"""
Hermes Life OS - Weekly Email Summary
=========================================
Sends the same self-contained HTML report demo/dashboard.py generates
(trend charts, correlations, retrospective, habit streaks) as an email -
a weekly check-in that lands in your inbox without you having to
remember to run the dashboard yourself.

Reuses the same SMTP settings as notifications.py's 'email' channel:
    HERMES_SMTP_HOST
    HERMES_SMTP_PORT      (default: 587)
    HERMES_SMTP_USER
    HERMES_SMTP_PASSWORD
    HERMES_SMTP_TO        (recipient; defaults to HERMES_SMTP_USER)

A plain-text fallback is included alongside the HTML for email clients
that don't render HTML. The embedded chart image uses a data: URI (the
same technique dashboard.py's saved HTML file uses) - this displays
correctly in most modern clients (Gmail, Apple Mail, web-based clients)
but historically some versions of Outlook desktop don't render inline
data: URI images. If your report arrives without the chart image
visible, that's most likely why - the rest of the report (correlations,
retrospective, habits) is plain HTML/text and unaffected.

This is a standalone command, not wired into the scheduler by default
(not everyone has SMTP configured) - schedule it yourself with your
OS's own task scheduler if you want it automatic:
    Linux/macOS (cron):  0 8 * * 1  hermes-life-os-weekly-email
    Windows (Task Scheduler): trigger weekly, action = same command

Usage:
    python demo/weekly_email.py
    python demo/weekly_email.py --days 30 --compare-days 7
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
from dashboard import build_dashboard_data, render_html
from notifications import send_html_email, NotificationError


def send_weekly_summary(days: int = 30, compare_days: int = 7) -> None:
    """Builds the dashboard report and emails it. Raises NotificationError
    (from notifications.py) if SMTP isn't configured or sending fails -
    callers should catch that rather than letting it crash silently."""
    data = build_dashboard_data(days, compare_days)
    html = render_html(data)
    plain = (
        f"Your Hermes Life OS weekly summary is ready - {data['entry_count']} "
        f"entries logged over the last {days} days. Open this email in an "
        f"HTML-capable client to see the full report with charts, "
        f"correlations, and habit streaks."
    )
    subject = f"Hermes Life OS - Weekly Summary ({storage.ACTIVE_PROFILE})"
    send_html_email(subject, html, plain)


def main():
    parser = argparse.ArgumentParser(description="Email the Hermes Life OS dashboard report")
    parser.add_argument("--days", type=int, default=30, help="How many days of history to include")
    parser.add_argument("--compare-days", type=int, default=7,
                        help="Size of the retrospective comparison window. Default 7.")
    parser.add_argument("--profile", default=None,
                        help="Named profile to summarize. Default: 'default'. "
                             "Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args()

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    if not storage.MEMORY_FILE.exists():
        print("No data yet - run a mode like 'onboard' or 'morning' first to start logging.")
        sys.exit(1)

    try:
        send_weekly_summary(args.days, args.compare_days)
    except NotificationError as e:
        print(f"Failed to send weekly summary: {e}")
        sys.exit(1)

    print(f"Weekly summary emailed (profile: {storage.ACTIVE_PROFILE}).")


if __name__ == "__main__":
    main()
