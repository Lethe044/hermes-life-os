"""The symptom trigger report: symptom days compared with other days."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

TODAY = date(2026, 10, 13)


def day(n):
    """The date n days before today."""
    return (TODAY - timedelta(days=n)).isoformat()


MIGRAINE_DAYS = [3, 7, 10, 14, 18, 22, 27]


def seed(storage, symptom_days=MIGRAINE_DAYS, window=40, sleep=True, stress=True, wine=True, water=False,
         workout=False, symptom="migraine", triggers=None):
    sleeps, mental, subs, hyd, fit, sym = [], [], [], [], [], []
    for i in range(window):
        bad = i in symptom_days
        d, before = day(i), day(i + 1)
        if sleep:
            sleeps.append({"id": f"s{i}", "date": d, "hours": 5.0 if bad else 7.5, "quality": 3 if bad else 7})
        if stress:
            mental.append({"id": f"m{i}", "date": before, "score": 8 if bad else 4, "trigger": "x"})
        if wine and bad:
            subs.append({"id": f"w{i}", "date": before, "substance": "Red Wine", "amount": 2, "unit": "glass"})
        if water:
            hyd.append({"id": f"h{i}", "date": before, "glasses": 2 if bad else 7})
        if workout and not bad:
            fit.append({"id": f"f{i}", "date": before, "type": "run", "duration": 30})
        if bad:
            sym.append({"id": f"y{i}", "date": d, "symptom": symptom, "severity": 7, "triggers": triggers or ["stress", "wine"]})
    storage.save_sleep(sleeps); storage.save_mental(mental); storage.save_substance(subs)
    storage.save_hydration({"today": 0, "goal": 8, "log": hyd}); storage.save_fitness(fit); storage.save_symptoms(sym)


@pytest.fixture()
def st(planner):
    import storage
    return storage


def report(planner, **kw):
    return planner.dispatch_tool("get_symptom_triggers", kw)


class TestReport:
    def test_finds_the_planted_patterns(self, planner, st):
        seed(st)
        out = report(planner, days=60).split("\n")
        assert out[0] == "What differs on migraine days (last 60 days: 7 migraine days, 53 other days):"
        body = "\n".join(out)
        assert "- Sleep the night before: 5.0h on migraine days vs 7.5h on other days (7 vs 33 days with data)." in body
        assert "- Sleep quality the night before: 3.0/10 on migraine days vs 7.0/10 on other days (7 vs 33 days with data)." in body
        assert "- Stress the day before: 8.0/10 on migraine days vs 4.0/10 on other days (7 vs 33 days with data)." in body
        assert "- Alcohol the day before: before 7 of 7 migraine days (100%) vs 0 of 34 other logged days (0%)." in body
        assert out[-2] == "Triggers you named: stress (7x), wine (7x)."
        assert out[-1] == "These are patterns in your own data, not causes, and not medical advice."

    def test_findings_are_ordered_strongest_first_and_capped(self, planner, st):
        import symptoms
        seed(st, water=True, workout=True)
        rep = symptoms.trigger_report("migraine", 60)
        effects = [f["effect"] for f in rep["findings"]]
        assert effects == sorted(effects, reverse=True) and len(rep["findings"]) == 5
        assert {f["factor"] for f in rep["findings"]} <= {"sleep_hours", "sleep_quality", "stress", "water", "alcohol", "workout", "caffeine", "nicotine"}

    def test_water_and_workouts(self, planner, st):
        seed(st, sleep=False, stress=False, wine=False, water=True, workout=True)
        out = report(planner, days=60)
        assert "- Water the day before: 2.0 glasses on migraine days vs 7.0 glasses on other days (7 vs 33 days with data)." in out
        assert "- A workout the day before: before 0 of 7 migraine days (0%) vs 32 of 33 other logged days (97%)." in out

    def test_a_flat_history_has_no_findings(self, planner, st):
        seed(st, sleep=False, stress=False, wine=False)
        import storage
        storage.save_sleep([{"id": f"s{i}", "date": day(i), "hours": 7.0, "quality": 6} for i in range(40)])
        out = report(planner, days=60)
        assert "- No clear difference in sleep, stress, water, caffeine, alcohol, nicotine or workouts (or too little logged to tell)." in out

    def test_small_differences_are_not_reported(self, planner, st):
        seed(st, wine=False, stress=False)
        import storage
        storage.save_sleep([{"id": f"s{i}", "date": day(i), "hours": 7.2 if i in MIGRAINE_DAYS else 7.5, "quality": 6} for i in range(40)])
        assert "Sleep the night before" not in report(planner, days=60)

    def test_noisy_overlap_is_not_reported(self, planner, st):
        seed(st, wine=False, stress=False)
        import storage
        # symptom days are 1h shorter on average but individual nights swing by 6h in both groups
        rows = []
        for i in range(40):
            base = 6.0 if i in MIGRAINE_DAYS else 7.0
            rows.append({"id": f"s{i}", "date": day(i), "hours": base + (3 if i % 2 else -3), "quality": 6})
        storage.save_sleep(rows)
        assert "Sleep the night before" not in report(planner, days=60)

    def test_too_few_days_with_data_skips_a_factor(self, planner, st):
        seed(st, sleep=False, stress=False, wine=False)
        import storage
        storage.save_sleep([{"id": f"s{i}", "date": day(i), "hours": 5.0, "quality": 3} for i in MIGRAINE_DAYS[:3]]
                           + [{"id": f"o{i}", "date": day(i), "hours": 8.0, "quality": 8} for i in (0, 1, 2, 4, 5)])
        assert "Sleep the night before" not in report(planner, days=60)

    def test_presence_needs_a_real_gap(self, planner, st):
        seed(st, sleep=False, stress=False, wine=False)
        import storage
        # wine the day before on 4 of 7 symptom days (57%) and on 55% of the other logged days
        subs = [{"id": f"w{i}", "date": day(i + 1), "substance": "wine", "amount": 1} for i in MIGRAINE_DAYS[:4]]
        subs += [{"id": f"x{i}", "date": day(i + 1), "substance": "wine", "amount": 1} for i in range(40) if i not in MIGRAINE_DAYS and i % 20 < 11]
        storage.save_substance(subs)
        assert "Alcohol the day before" not in report(planner, days=60)

    def test_substance_groups(self, planner, st):
        import symptoms
        seed(st, sleep=False, stress=False, wine=False)
        import storage
        storage.save_substance([{"id": f"c{i}", "date": day(i + 1), "substance": "Espresso", "amount": 3} for i in MIGRAINE_DAYS]
                               + [{"id": f"n{i}", "date": day(i + 1), "substance": "cigarettes", "amount": 5} for i in MIGRAINE_DAYS])
        rep = symptoms.trigger_report("migraine", 60)
        assert {f["factor"] for f in rep["findings"]} == {"caffeine", "nicotine"}

    def test_the_most_frequent_symptom_is_the_default(self, planner, st):
        seed(st)
        import storage
        storage.save_symptoms(storage.load_symptoms() + [{"id": "q", "date": day(1), "symptom": "nausea", "severity": 3}])
        assert report(planner, days=60).startswith("What differs on migraine days")
        assert "Only 1 day(s) with nausea" in report(planner, symptom="Nausea", days=60)

    def test_only_symptom_days_inside_the_window_count(self, planner, st):
        seed(st)
        out = report(planner, days=14)    # keeps the 3, 7, 10 and 14-day-old... 14 days = day(0)..day(13)
        assert "3 migraine days" in out or "Only 3 day(s)" in out

    def test_not_enough_symptom_days(self, planner, st):
        seed(st, symptom_days=[3, 7, 10])
        assert report(planner, days=60) == "Only 3 day(s) with migraine in the last 60 days - at least 4 are needed to compare them with the other days."

    def test_no_symptoms_at_all(self, planner, st):
        assert report(planner) == "No symptoms logged in the last 90 days, so there is nothing to compare."

    def test_two_entries_on_one_day_count_once(self, planner, st):
        seed(st, symptom_days=[3, 7, 10, 14])
        import storage
        storage.save_symptoms(storage.load_symptoms() + [{"id": "dup", "date": day(3), "symptom": "migraine", "severity": 2}])
        assert "4 migraine days" in report(planner, days=60)

    def test_named_triggers_even_without_other_data(self, planner, st):
        seed(st, sleep=False, stress=False, wine=False, triggers=["noise", "heat"])
        out = report(planner, days=60)
        assert "Triggers you named: noise (7x), heat (7x)." in out

    @pytest.mark.parametrize("days", [13, 366, "x", True, 0, -5, 3.5])
    def test_bad_days(self, planner, st, days):
        assert report(planner, days=days).startswith("Cannot compare symptom days: days must be")

    def test_bad_symptom_name(self, planner, st):
        assert report(planner, symptom=5).startswith("Cannot compare symptom days: ")

    def test_damaged_stores_do_not_break_it(self, planner, st):
        seed(st)
        import storage
        storage.save_sleep(storage.load_sleep() + ["x", None, {"date": day(2), "hours": "lots"}, {"hours": 5}])
        storage.save_mental(["junk", {"date": day(1), "score": None}])
        storage.save_hydration({"log": "nope"})
        storage.save_fitness({"not": "a list"})
        out = report(planner, days=60)
        assert out.startswith("What differs on migraine days") and "Sleep the night before" in out

    def test_meditation_rows_are_not_stress(self, planner, st):
        import symptoms
        seed(st, sleep=False, stress=False, wine=False)
        import storage
        storage.save_mental([{"id": f"m{i}", "date": day(i + 1), "type": "meditation", "score": 9 if i in MIGRAINE_DAYS else 1} for i in range(40)])
        assert symptoms.trigger_report("migraine", 60)["findings"] == []

    def test_the_summary_tool_is_unchanged(self, planner, st):
        seed(st)
        assert planner.dispatch_tool("get_symptom_summary", {"days": 30}).startswith("Symptoms in the last 30 days")
