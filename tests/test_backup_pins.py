"""Pinned backups are never rotated away."""

from __future__ import annotations

import pytest


def d(p, tool, args=None):
    return p.dispatch_tool(tool, args or {})


def make(p, stamps):
    import backup
    from datetime import datetime
    out = []
    for s in stamps:
        out.append(backup.run_backup(keep=50, now=datetime.strptime(s, "%Y-%m-%d-%H%M%S")))
    return out


STAMPS = ["2026-10-01-100000", "2026-10-02-100000", "2026-10-03-100000", "2026-10-04-100000"]


class TestPin:
    def test_pin_latest_and_by_name(self, planner):
        make(planner, STAMPS)
        assert d(planner, "pin_backup") == "Pinned backup-2026-10-04-100000.json: it is kept until you unpin it, however many newer backups are written."
        assert d(planner, "pin_backup", {"backup": "10-02"}).startswith("Pinned backup-2026-10-02-100000.json")
        import backup
        assert backup.pinned_names() == ["backup-2026-10-02-100000.json", "backup-2026-10-04-100000.json"]

    def test_errors(self, planner):
        assert d(planner, "pin_backup") == "Not pinned: there are no backups yet. Use backup_now first."
        make(planner, STAMPS)
        assert d(planner, "pin_backup", {"backup": "zzz"}).startswith("Not pinned: no backup matches 'zzz'")
        assert d(planner, "pin_backup", {"backup": "2026-10"}).startswith("Not pinned: '2026-10' matches 4 backups")
        d(planner, "pin_backup")
        assert d(planner, "pin_backup") == "Not pinned: backup-2026-10-04-100000.json is already pinned."

    def test_at_most_ten(self, planner):
        import backup
        make(planner, [f"2026-10-{n:02d}-100000" for n in range(1, 13)])
        for n in range(1, 11):
            d(planner, "pin_backup", {"backup": f"2026-10-{n:02d}"})
        assert d(planner, "pin_backup", {"backup": "2026-10-11"}) == "Not pinned: 10 backups are pinned already. Unpin one first."
        assert len(backup.pinned_names()) == 10

    def test_unpin(self, planner):
        make(planner, STAMPS)
        d(planner, "pin_backup", {"backup": "10-01"})
        assert d(planner, "unpin_backup", {"backup": "10-01"}).startswith("Unpinned backup-2026-10-01-100000.json")
        assert d(planner, "unpin_backup", {"backup": "10-01"}) == "Not unpinned: backup-2026-10-01-100000.json is not pinned."
        assert d(planner, "unpin_backup", {"backup": "zzz"}).startswith("Not unpinned: no backup matches")


class TestRotation:
    def test_pinned_backups_survive_and_do_not_count_towards_keep(self, planner):
        import backup
        files = make(planner, STAMPS)
        d(planner, "pin_backup", {"backup": "10-01"})
        removed = backup.rotate_backups(backup.backups_dir(), 2)
        assert [p.name for p in removed] == ["backup-2026-10-02-100000.json"]
        left = [p.name for p in backup._list_backups(backup.backups_dir())]
        assert left == ["backup-2026-10-01-100000.json", "backup-2026-10-03-100000.json", "backup-2026-10-04-100000.json"]
        assert files[0].exists()

    def test_run_backup_rotation_keeps_pins(self, planner):
        import backup
        from datetime import datetime
        make(planner, STAMPS[:2])
        d(planner, "pin_backup", {"backup": "10-01"})
        backup.run_backup(keep=1, now=datetime(2026, 10, 5, 10))
        names = [p.name for p in backup._list_backups(backup.backups_dir())]
        assert names == ["backup-2026-10-01-100000.json", "backup-2026-10-05-100000.json"]

    def test_unpinned_again_it_rotates(self, planner):
        import backup
        make(planner, STAMPS)
        d(planner, "pin_backup", {"backup": "10-01"})
        d(planner, "unpin_backup", {"backup": "10-01"})
        backup.rotate_backups(backup.backups_dir(), 2)
        assert [p.name for p in backup._list_backups(backup.backups_dir())] == ["backup-2026-10-03-100000.json", "backup-2026-10-04-100000.json"]

    def test_negative_keep_is_still_refused(self, planner):
        import backup
        with pytest.raises(ValueError):
            backup.rotate_backups(backup.backups_dir(), -1)

    def test_a_pin_whose_file_is_gone_is_forgotten(self, planner):
        import backup
        files = make(planner, STAMPS)
        d(planner, "pin_backup", {"backup": "10-01"})
        files[0].unlink()
        assert backup.pinned_names() == []

    @pytest.mark.parametrize("content", ["not json", "{}", "[1, null, {}]", ""])
    def test_a_damaged_pin_file_means_nothing_is_pinned(self, planner, content):
        import backup
        make(planner, STAMPS[:1])
        backup._pinned_path(backup.backups_dir()).write_text(content, encoding="utf-8")
        assert backup.pinned_names() == []
        assert d(planner, "pin_backup").startswith("Pinned ")

    def test_the_pin_file_is_not_mistaken_for_a_backup(self, planner):
        import backup
        make(planner, STAMPS[:1])
        d(planner, "pin_backup")
        assert len(backup._list_backups(backup.backups_dir())) == 1 and len(backup.list_backups()) == 1


class TestStatus:
    def test_status_lists_pins(self, planner):
        make(planner, STAMPS[:2])
        assert "Pinned" not in d(planner, "get_backup_status")
        d(planner, "pin_backup", {"backup": "10-01"})
        assert "Pinned (kept whatever the keep count): backup-2026-10-01-100000.json." in d(planner, "get_backup_status")
