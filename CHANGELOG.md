# Changelog

All notable changes to Hermes Life OS, newest first. The latest releases are also summarised in the [README](README.md#whats-new).

**v1.51.0 - Projects and Waiting For**
- New **projects**: `add_project`, `get_projects`, `get_project`, `update_project`,
  `add_project_task`, `delete_project`. A project is an outcome that needs several tasks;
  every project owns a tag and the tasks carrying it belong to it. Hermes shows progress, the
  next action and flags projects that are overdue or have no open task. The agenda lists
  project actions due today and a nudge points at stuck or overdue projects.
- New **waiting for** list: `add_waiting`, `get_waiting`, `chase_waiting`, `resolve_waiting`,
  `delete_waiting`. Track what you need back from someone, with a follow-up date (a week out
  by default). Items due for a follow-up show in the agenda and nudges; chasing pushes the
  date out and resolving closes the item.
- Recently deleted now labels waiting items by what you were waiting for.
- Doctor, repair suggestions, search, backup, restore, export and recently deleted cover the
  two new stores.
- 37 new tests - suite grew from 5017 to 5054.

**v1.50.0 - Flashcards and Net Worth**
- New **flashcards** with spaced repetition (Leitner boxes): `add_flashcards`,
  `review_flashcards`, `reveal_flashcard`, `answer_flashcard`, `get_flashcard_stats`,
  `delete_flashcard`. A correct answer moves a card up a box (it returns after 1, 3, 7, 16 and
  35 days), a wrong one sends it back to box 1 for tomorrow. The agenda and a nudge show how
  many cards are due.
- New **net worth**: `set_account_balance`, `get_net_worth`, `get_net_worth_trend`,
  `delete_account`. Record what you own and owe whenever you look at it; Hermes keeps each
  account's history and shows net worth today, the change since the last update and a
  month-by-month trend. A nudge appears after five weeks without an update.
- Recently deleted now labels flashcards by their front and weekly reviews by their week.
- Doctor, repair suggestions, search, backup, restore, export and recently deleted cover the
  two new stores.
- 39 new tests - suite grew from 4978 to 5017.

**v1.49.0 - Inbox and Weekly Review**
- New **inbox**: `add_to_inbox`, `get_inbox`, `process_inbox_item`, `delete_inbox_item`.
  Capture anything the moment it crosses your mind, then turn it into a task, a note, a
  library item or one of today's priorities. The agenda shows what is unsorted and a nudge
  appears when items have waited three days or the inbox reaches ten.
- New **weekly review**: `start_weekly_review`, `save_weekly_review`, `get_weekly_reviews`,
  `delete_weekly_review`. A guided end-of-week ritual: the facts of the week (tasks,
  priorities, time blocks, overdue, inbox, life wheel), three questions, a 1 to 5 rating and
  up to five focus items for next week that can become tasks. Friday to Sunday a nudge asks
  for it once you have done one.
- The tool reference and the README tool count stay in sync through tests.
- Doctor, repair suggestions, search, backup, restore, export and recently deleted cover the
  two new stores.
- 38 new tests - suite grew from 4940 to 4978.

**v1.48.0 - Daily Priorities, Plan My Day, Life Wheel, Library, Calendar Export**
- New **daily priorities** (the "Big 3"): `add_priority`, `get_priorities`, `complete_priority`,
  `carry_over_priorities`, `delete_priority`. At most three per day, free text or an open task
  (finishing the priority finishes the task), a streak of days with every priority done, and
  the agenda, the nudges and the closing summary show what is still open.
- New **plan my day**: `plan_my_day` fits priorities, overdue and due tasks into the free
  gaps of your day plan. It shows a proposal first; `apply=true` saves time blocks linked to
  the tasks. Tasks take an optional `minutes` estimate (`add_task`, `update_task`).
- New **life wheel**: `log_life_wheel`, `get_life_wheel`, `delete_wheel_checkin`. Rate eight
  areas from 1 to 10, see bars, the change since the last check-in and the lowest areas, and get
  a nudge after five weeks without a check-in.
- New **library**: `add_library_item`, `get_library`, `update_library_item`,
  `finish_library_item`, `suggest_library_item`, `get_library_stats`, `delete_library_item`.
  One backlog for books, movies, shows, games, podcasts and courses.
- New **calendar export**: `export_calendar` writes an `.ics` file (time blocks, task due
  dates, birthdays, countdowns, trips, expiry dates, chores, renewals, decision reviews) with
  stable ids, so a newer import updates earlier events instead of duplicating them.
- New **tool reference** `docs/TOOLS.md`, generated from the schemas and checked by a test.
- README restructured (quick tour, contents, demo); release history moved to
  [CHANGELOG.md](CHANGELOG.md); added SECURITY.md and a pull request template.
- Doctor, repair suggestions, search, backup, restore, export and recently deleted cover the
  three new stores.
- 81 new tests - suite grew from 4859 to 4940.

**v1.47.0 - Recently Deleted, Recommendation Ledger, Pinned Backups**
- New **recently deleted**: `get_trash`, `restore_deleted`, `empty_trash`. Every
  planner delete or clear tool now keeps what it removed for 30 days, so a wrong
  delete can be undone. A test fails when a new delete tool is not covered.
- New **recommendation ledger**: `get_recommendation_history`,
  `mark_recommendation`. Suggestions from `get_recommendations` are filed; a
  followed one is compared with the metric before and after.
- New **pinned backups**: `pin_backup`, `unpin_backup`. Pinned backups survive
  rotation and do not count towards the keep limit.
- The doctor, `get_repair_suggestions`, `search_everything`, backup, restore,
  export and rekey cover the two new stores (trash and recs).
- Ideas for these three came from a look at Matt Abate's life-distributable
  (approval gates, a recommendation ledger, backups that cannot be deleted by
  the agent); the code is our own.
- 137 new tests - suite grew from 4722 to 4859.

**v1.46.1 - Subscription renewals keep their day of the month**
- Fix: `pay_subscription` saved the clamped renewal date as the new schedule, so
  a monthly renewal on the 31st drifted to the 28th for good (Jan 31, Feb 28,
  Mar 28, Apr 28). Quarterly renewals from Nov 30 and yearly ones from Feb 29
  drifted the same way. Every subscription now remembers the date its schedule
  was set from (`anchor`) and counts each renewal from it, so Jan 31 is followed
  by Feb 28, Mar 31 and Apr 30. Paying late, catching up after missed payments,
  resuming a cancelled subscription and the unpaid roll-forward all keep the day.
  Editing the date or the cycle by hand starts a new schedule from that date.
  A subscription that already drifted before this release stays where it is: set
  its real date once with `update_subscription` and it holds from then on.
- Thanks to Matt Abate for the report (issue #34).
- 24 new tests - suite grew from 4698 to 4722.

**v1.46.0 - Chores, Expiry Dates, Routines, Gift Ideas, Decisions**
- New **chores**: `add_chore`, `complete_chore`, `get_chores`, `update_chore`,
  `delete_chore` for anything that repeats, counted from the last time it was done.
- New **expiry dates**: `add_expiry`, `get_expiries`, `renew_expiry`,
  `update_expiry`, `delete_expiry` with a reminder window and renewal history.
- New **routines**: `add_routine`, `get_routines`, `check_routine_step`,
  `update_routine`, `delete_routine` with per-day ticks and streaks.
- New **gift ideas**: `add_gift_idea`, `get_gift_ideas`, `update_gift_idea`,
  `delete_gift_idea`, linked to birthdays in the people list.
- New **decision journal**: `add_decision`, `get_decisions`, `review_decision`,
  `update_decision`, `delete_decision` with confidence versus outcome.
- New **`get_week_ahead`**: one calendar over everything with a date.
- Due chores, expiring documents, gifts to buy and decisions to review appear in
  the proactive nudges and in `get_today_agenda`; routines still to finish are
  in the agenda too. The closing summary, `search_everything`, the doctor and
  `get_repair_suggestions` cover the five new stores; backup, restore, export
  and rekey do as well.
- 379 new tests - suite grew from 4319 to 4698.

**v1.45.0 - Time Blocks, Objectives, Recipes, Trips**
- New **time blocks**: `add_time_block`, `get_day_plan`, `update_time_block`,
  `delete_time_block`, `finish_time_block`, `find_free_time`, `schedule_task`,
  `get_time_allocation`.
- New **objectives and key results**: `add_objective`, `add_key_result`,
  `record_key_result`, `get_okrs`, `update_okr`, `delete_okr` with pace.
- New **recipes and meal plan**: `add_recipe`, `get_recipes`, `get_recipe`,
  `update_recipe`, `delete_recipe`, `suggest_recipes`, `plan_meal`,
  `get_meal_plan`, `clear_meals`, `log_planned_meal`, `shopping_from_plan`.
- New **trips**: `add_trip`, `get_trips`, `get_trip`, `update_trip`,
  `delete_trip`, `add_packing_items`, `pack_items`, `remove_packing_items`,
  `add_itinerary_item`, `remove_itinerary_item`.
- New **`get_symptom_triggers`**, **`search_everything`**,
  **`get_closing_summary`** and **`get_repair_suggestions`**.
- Upcoming blocks, objectives about to end and trips appear in the proactive
  nudges and in `get_today_agenda`; the doctor checks the five new stores;
  backup, restore, export and rekey cover them.
- 665 new tests - suite grew from 3654 to 4319.

**v1.44.0 - Income, Debts, Countdowns, Supplies**
- New **income** tracker: `log_income` and `get_cash_flow` (income vs logged
  spending per month: net, savings rate, average, sources). Income works with
  `list_logs`, `edit_log`, `delete_log`, `undo_last_log`, backdating and
  `log_many`.
- New **debts**: `add_debt`, `record_debt_payment`, `get_debts`, `update_debt`,
  `delete_debt` for money you owe and money owed to you, with partial payments,
  due dates and overdue flags.
- New **countdowns**: `add_countdown`, `get_countdowns`, `update_countdown`,
  `delete_countdown` for days until and since, with yearly anniversaries.
- New **supplies**: `add_supply`, `refill_supply`, `get_supplies`,
  `update_supply`, `delete_supply` with remaining count and run-out date.
- Debts that are due, countdowns and supplies about to run out appear in the
  proactive nudges (now up to three planner items) and in `get_today_agenda`;
  the doctor checks the four new stores and future-dated income; backup,
  restore, export and rekey cover them.
- Fix: the `date` property of `log_symptom` was shared with other schemas.
- 315 new tests - suite grew from 3339 to 3654.

**v1.43.0 - Lists, Savings Goals, Symptoms, Notes**
- New **lists**: `add_list_items`, `get_list`, `get_lists`, `check_list_item`,
  `remove_list_items`, `clear_checked_items`, `delete_list` for the shopping
  list and any other named checklist.
- New **savings goals**: `add_savings_goal`, `contribute_to_savings`,
  `get_savings`, `update_savings_goal`, `delete_savings_goal` with progress,
  real pace, estimated finish day and the monthly amount needed for a deadline.
- New **symptom tracker**: `log_symptom` and `get_symptom_summary` (severity,
  duration, triggers, frequency trend, worst weekday, sleep comparison).
  Symptoms are a tracker like the others: `list_logs`, `edit_log`,
  `delete_log`, `undo_last_log`, backdating and `log_many` work on them.
- New **notes**: `add_note`, `list_notes`, `search_notes`, `update_note`,
  `delete_note` with tags and pins.
- Savings goals close to their deadline appear in the proactive nudges and in
  `get_today_agenda`; the doctor checks the four new stores and now also looks
  for future-dated body readings and symptoms; backup, restore, export and
  rekey cover the new stores.
- 354 new tests - suite grew from 2985 to 3339.

**v1.42.0 - Planner: Tasks, Body Metrics, Subscriptions, People, Agenda**
- New **tasks**: `add_task`, `list_tasks`, `complete_task`, `update_task`,
  `delete_task`, `get_task_summary`, `clear_done_tasks` with natural due dates,
  priority, tags and daily/weekdays/weekly/monthly repeats.
- New **body metrics**: `log_body_metric`, `get_body_trend`, `set_body_goal`
  for weight, body fat, waist, hips, resting heart rate, blood pressure,
  glucose, temperature and SpO2, with unit conversion, weekly trend and goal
  ETA. Body readings join `list_logs`, `edit_log`, `delete_log`, backdating and
  `log_many`.
- New **subscriptions**: add, list, update, cancel, resume, delete, summary and
  `pay_subscription` (logs the expense), with monthly-equivalent totals and
  month-end-safe renewal dates.
- New **people**: birthdays, keep-in-touch goals, contact history,
  `get_people_due`.
- New **`get_today_agenda`** combining tasks, reminders, renewals, birthdays,
  overdue catch-ups, streaks at risk and budget alerts.
- Proactive nudges cover overdue tasks, renewals and people; the doctor gets a
  planner check; backup, restore, export and rekey cover the four new stores.
- `clock.py` gains `parse_day` and `add_months`.
- 407 new tests - suite grew from 2578 to 2985.

**v1.41.0 - Habit Check-ins, Day View, Batch Logging**
- **Fix:** `update_habit` counted every call as a new day. Checking a habit in
  twice on one day inflated the streak (and the freeze counter), and a gap of
  several days never reset it. Check-ins are now one per day, a missed day
  restarts the streak, and `update_habit` takes an optional `date` (recorded
  for the analytics, running streak untouched).
- Hydration joins the entry tools (`list_logs`, `edit_log`, `delete_log`,
  `undo_last_log`, `delete_entry` cascade): the glass log can be corrected and
  the running "today" counter is recomputed.
- New `get_day_log` (everything logged on a day, with ids), `search_logs`
  (text search across the trackers), `find_duplicate_logs` (identical entries
  on the same day, report only) and `log_many` (up to 50 logs in one call,
  validated up front).
- Doctor: the entry-id check now covers hydration rows.
- 99 new tests - suite grew from 2479 to 2578.

**v1.40.0 - Fix Any Log, Undo, Catch-Up**
- New **`list_logs`, `edit_log`, `delete_log`** for 11 trackers: until now
  only expenses could be corrected, so a wrong meal or a duplicate workout
  stayed in every average and streak. Edits are validated all-or-nothing and
  keep the memory-journal entry in sync.
- New **`undo_last_log`**: removes the most recent log of a tracker, or of
  whatever was logged last.
- New **`get_logging_gaps`**: days with nothing logged (one line per used
  tracker, or every empty day for one tracker), to fill in with `date`.
- `log_dream` accepts `date`. Every new log carries a persistent `id`, and its
  journal entry a matching `log_id`.
- `delete_entry` on a linked journal entry now also removes the tracker row
  (before it left the row behind, still counted in summaries).
- Doctor: new entry-id check (duplicate ids, orphaned journal links).
- 192 new tests - suite grew from 2287 to 2479.

**v1.39.0 - Local Days, Backdating, Fixing Expenses**
- **Fix:** streaks, "last N days" windows and the budget month used UTC
  while entries were stamped with local dates. Outside UTC a dose logged
  "today" could miss today's streak for hours, an expense after midnight on
  the 1st counted in the previous month's budget, and in UTC+14 the
  medication streak read 0 most of the day. A single `demo/clock.py` now
  defines the user's day for all dated trackers (the UTC memory journal
  analytics are unchanged on purpose).
- New `LIFE_OS_DAY_START_HOUR` (0-12) for night owls; invalid values are
  flagged by the doctor.
- **Backdating:** 13 log tools accept an optional `date`, with validation
  (no future, at most 365 days back).
- **Expenses can be fixed:** new `list_expenses`, `update_expense` and
  `delete_expense`; expenses carry ids and stay in sync with the memory
  journal.
- Doctor: new clock and future-dated-entries checks.
- Tests run under a pinned clock, so they cover midnight boundaries in any
  time zone; the suite was run under UTC, Istanbul, Kiritimati (+14), Pago
  Pago (-11) and Los Angeles.
- 270 new tests - suite grew from 2017 to 2287.

**v1.38.0 - Data Safety: Complete Backups, Restore, Doctor**
- **Fix (data loss):** `hermes-life-os-rekey` only re-encrypted 9 of the 18
  data files. After a passphrase change the others (spending, reminders,
  budgets, ...) could not be decrypted and read back as empty, and the old
  key was unrecoverable once the salt rotated. Re-keying now covers every
  store. A single registry (`storage.DATA_STORES`) drives backup, restore
  and re-keying, and a test fails if a new data file is not registered.
- **Fix:** backups and `export_data` json now include every data store, not
  just nine, plus a `_meta` block. The nightly backup used to leave out
  spending, social, substance, reading, medication, achievements,
  templates, budgets and reminders.
- New **`hermes-life-os-restore`**: restores a backup with up-front
  validation, `--dry-run`, `--only`, `--list`/`--latest`, a never-rotated
  `pre-restore-*` safety copy and a confirmation prompt. Old backups
  restore without wiping the sections they lack.
- Backups are **encrypted** when `LIFE_OS_ENCRYPTION_KEY` is set (before,
  an encrypted profile left plaintext backups behind).
- New **`hermes-life-os-doctor`** and `run_health_check`: a read-only
  check of stores, the memory journal, leftover temp files, backups,
  reminders and budgets.
- New `get_backup_status` tool, and a proactive nudge when the newest
  backup is 3 or more days old or unreadable.
- **Fix:** `backup_now` could delete every backup, including the one it had
  just written, if `keep` was 0 or invalid. It now always keeps at least one.
- Reminders: one-off dated reminders, `remind_me_in`, `snooze_reminder`,
  `clear_past_reminders`.
- Budgets: per-budget `alert_pct`, input validation for `set_budget`, and
  `suggest_budgets`.
- **Fix (tests):** `test_with_data_surfaces_finding` failed every night
  between 00:00 and the UTC offset (it mixed local and UTC dates); the
  suite now passes in UTC+14, UTC-11 and UTC-8 as well as UTC and UTC+3.
- 512 new tests - suite grew from 1505 to 2017.

**v1.37.0 - Live Reminders & Budget Forecasting**
- **Reminders are delivered.** `scheduler.run_scheduler()` gained a
  backwards-compatible `dynamic_source` hook and `run_scheduler.py`
  wires `reminders.scheduler_source` into it, so timed reminders fire
  through the configured notification channel (once per day, with a
  small grace window; a broken source or notifier never stops the loop).
- New reminder tools: `update_reminder`, `pause_reminder`,
  `resume_reminder`, `get_todays_reminders`. Times are normalized to
  24-hour `HH:MM` (`9am`, `9:30pm`), and `create_reminder` now tells the
  user when a time cannot be scheduled.
- New budget tools: `get_budget_forecast` (month-end projection and
  per-day allowance), `get_budget_history` (last N completed months) and
  `get_unbudgeted_spending` (spending outside any budget).
- Over-budget and nearly-used-up budgets now appear in the proactive
  nudge check and `get_nudges`.
- **Fix:** spending categories now match budgets case-insensitively. An
  expense logged as "Food" was previously not counted against a "food"
  budget.
- 151 new tests - suite grew from 1354 to 1505.

**v1.36.0 - Budgets & Reminders**
- New **Budget Layer** (`demo/budgets.py`, `set_budget`/
  `get_budget_status`/`list_budgets`/`delete_budget`): the project's
  first forward-looking money tool, alongside the existing
  retrospective spending features. A per-category monthly limit is
  compared against real spending logged so far this calendar month
  (via `load_spending`), flagging categories that are over budget.
- New **Reminders Layer** (`demo/reminders.py`, `create_reminder`/
  `list_reminders`/`delete_reminder`): user-defined reminders with an
  optional time hint and days of the week, finally giving a person a
  way to define their own reminder beyond `scheduler.py`'s hardcoded
  schedule. Scoped to storage/CRUD only in this round - not yet wired
  into `run_scheduler()` or live notification delivery.
- 51 new tests - suite grew from 1303 to 1354.

**v1.35.0 - List, Delete Habits & Goals**
- New **`list_habits`**: shows every habit regardless of streak status
  - fills a real blind spot where a brand-new or fully-reset habit
  (0-day streak, no past best) was invisible to
  `get_habit_milestones`, `get_habit_pb_progress`, and the health
  dashboard, all of which only cover habits with an active or past
  streak.
- New **`delete_habit`** and **`delete_goal`**: basic CRUD completion -
  previously there was no way to remove a habit or goal at all once
  created, only `delete_entry` for individual memory entries.
- 10 new tests - suite grew from 1293 to 1303.

**v1.34.0 - Habit-Linked Goals & Quick-Log Templates**
- New **Habit-Linked Goals**: `update_goal` now accepts `linked_habit`
  + `target_streak` as a third progress-tracking mode alongside manual
  and metric-linked - a goal like "hit a 30-day meditation streak" now
  auto-tracks itself from the habit's real current streak via new
  `compute_habit_goal_progress()`. `check_goal_progress` refreshes
  these the same way it already refreshes metric-linked goals.
- New **Quick-Log Templates** (`demo/templates.py`,
  `save_log_template`/`use_log_template`/`list_log_templates`/
  `delete_log_template`): save a named shortcut for a specific `log_*`
  tool call with fixed parameters and replay it later with one call.
  Restricted to `log_*` tools only, so a template can never trigger
  anything beyond adding a new log entry.
- 36 new tests - suite grew from 1257 to 1293.

**v1.33.0 - Life Review Conversational, Two More Matplotlib Crash Fixes**
- **Bug fix**: found the same matplotlib-crash bug fixed in `wrapped.py`
  last release in two more places - `demo/dashboard.py` and
  `demo/life_review.py` both imported matplotlib at module level and
  called `sys.exit(1)` if it was missing. Both now use a shared,
  lazily-evaluated `_get_pyplot()` helper that raises a normal
  `ImportError` only when a chart is actually being rendered.
  `build_dashboard_data()` and `build_life_review_data()` need no
  plotting library at all now; the CLIs' behavior is unchanged.
- New **`get_life_review`**: a text version of `demo/life_review.py`'s
  full period review (life score trend, best/toughest day, correlation
  insights, retrospective comparison, badges earned), via a new
  `format_life_review_summary()` - the deeper counterpart to
  `get_wrapped`'s quick recap.
- 9 new tests - suite grew from 1248 to 1257.

**v1.32.0 - Proactive Nudges & Wrapped, Now Conversational**
- New **`get_nudges`**: exposes the scheduler's existing deterministic
  anomaly and off-track-goal checker (`demo/nudges.py`) on demand,
  instead of only running on a schedule.
- New **`get_wrapped`**: a text version of `demo/wrapped.py`'s
  "Spotify Wrapped"-style period recap, via a new
  `format_wrapped_summary()` alongside the existing image-rendering
  `render_wrapped_image()`.
- **Bug fix**: `wrapped.py` used to import matplotlib at module level
  and call `sys.exit(1)` if it was missing - harmless for a CLI
  script, but it would have crashed the whole bot/API process the
  first time `get_wrapped` ran anywhere without matplotlib installed.
  The import is now lazy (inside `render_wrapped_image()` only) and
  raises a normal `ImportError`; the CLI's `main()` still exits
  cleanly with the same message as before.
- 10 new tests - suite grew from 1238 to 1248.

**v1.31.0 - Correlation Refactor, Reading Mood Impact, Insights Digest**
- **Refactored** Habit Mood Impact, Substance-Sleep Impact, Social
  Mood Impact, and Workout Mood Impact to share one implementation in
  new `demo/correlation_utils.py`, instead of four nearly-identical
  same-calendar-day comparison implementations. Public functions,
  return shapes, and wording are all unchanged - verified by the full
  existing test suite for all four passing unmodified.
- New **Reading Mood Impact** (`demo/reading_correlation.py`,
  `get_reading_mood_impact`): the same day-vs-day mood comparison, for
  reading sessions - made cheap to add by the refactor above.
- New **Insights Digest** (`demo/insights_digest.py`,
  `get_insights_digest`): runs every correlation check at once and
  surfaces only the findings with a meaningful difference, instead of
  needing to call seven-plus separate correlation tools to find out if
  anything stands out.
- 25 new tests - suite grew from 1213 to 1238.

**v1.30.0 - Workout Mood Impact, Conversational Export & Backup**
- New **Workout Mood Impact** (`demo/workout_correlation.py`,
  `get_workout_mood_impact`): compares average mood on workout days
  versus non-workout days.
- New **Conversational Export & Backup** (`demo/export_tool.py`,
  `export_data` and `backup_now`): exposes the existing
  `data_export.py` (JSON/CSV/Markdown) and `backup.py` (rotating
  backups) CLI scripts as ordinary dispatch_tool calls, so they can be
  triggered from chat instead of only from the command line. Picks a
  sensible default output path under the active profile's `exports/`
  or `backups/` directory.
- README badge fix: swapped the PyPI Downloads badge from
  shields.io's `pypi/dm` (which depends on pypistats.org and
  intermittently shows "rate limited by upstream service") to
  pepy.tech's own badge service.
- 22 new tests - suite grew from 1191 to 1213.

**v1.29.0 - Social Insights, Social Mood Impact, Medication Streak**
- New **Social Insights** (`demo/social_insights.py`,
  `get_social_insights`): recent social interactions broken down by
  who they were with - time spent, average quality, and the most
  frequent contact.
- New **Social Mood Impact** (`demo/social_correlation.py`,
  `get_social_mood_impact`): compares average mood on days with a
  logged social interaction versus days without one.
- New **Medication Streak** (`demo/medication_streak.py`,
  `get_medication_streak`): current and longest consecutive-day streak
  of taking a specific medication/supplement, complementing the
  existing overall-percentage Medication Adherence.
- Also refreshed the README badge row: added PyPI downloads, dynamic
  Python-versions (from PyPI metadata instead of a static "3.10+"),
  GitHub stars, and last-commit badges alongside the existing
  Tests/PyPI-version/License badges.
- 28 new tests - suite grew from 1163 to 1191.

**v1.28.0 - Reading Pace, Spending Trends, Substance-Sleep Impact**
- **Enhanced `log_reading`**: now accepts an optional `total_pages`
  for a book, enabling a real finish estimate.
- New **Reading Pace** (`demo/reading_pace.py`, `get_reading_pace`):
  pages/day for a specific book, and an estimated finish date once a
  total page count has been logged for it.
- New **Spending Trends** (`demo/spending_trends.py`,
  `get_spending_trends`): compares spending per category between a
  recent window and the equal-length window before it - which
  categories are trending up or down, complementing the existing
  single-window Spending Summary.
- New **Substance-Sleep Impact** (`demo/substance_correlation.py`,
  `get_substance_sleep_impact`): compares average sleep hours on days
  a substance was logged versus days it wasn't.
- 39 new tests - suite grew from 1124 to 1163.

**v1.27.0 - Habit Consistency, Mood Impact, and Overview**
- **Enhanced `update_habit`**: every check-in (done, missed, or
  protected with a freeze) is now also recorded as a
  `habit_completion` entry in the shared memory log, giving Hermes a
  real per-check-in history to analyze instead of only the current
  streak counters in `habits.json`.
- New **Habit Consistency** (`demo/habit_consistency.py`,
  `get_habit_consistency`): percentage of successful check-ins per
  habit, a different and sometimes more honest signal than the current
  streak alone.
- New **Habit Mood Impact** (`demo/habit_correlation.py`,
  `get_habit_mood_impact`): compares average mood on days a habit was
  completed versus missed - a genuine correlation feature, naturally
  forward-looking since it depends on check-in history recorded from
  here on.
- New **Habit Overview** (`demo/habit_overview.py`,
  `get_habit_overview`): a single combined dashboard over Habit
  Milestones, Habit Personal Bests, and Habit Consistency for a
  general "how are my habits doing" question.
- 33 new tests - suite grew from 1091 to 1124.

**v1.26.0 - Hydration, Focus, Dream, and Stress Summaries**
- New **Hydration Summary** (`demo/hydration_summary.py`,
  `get_hydration_summary`): average daily intake vs. goal, days the
  goal was met, and the current consecutive-day goal-met streak,
  rebuilt from the raw hydration log rather than the single "today"
  counter.
- New **Focus Summary** (`demo/focus_summary.py`, `get_focus_summary`):
  totals, average duration/quality, completion rate, total
  distractions, and the most common task.
- New **Dream Recap** (`demo/dream_recap.py`, `get_dream_recap`):
  totals, average vividness, most common tone, and symbols/emotions
  that recur across multiple distinct dreams. Reads from
  `get_recent_memory` since dreams have no dedicated storage file.
- New **Stress Summary** (`demo/stress_summary.py`,
  `get_stress_summary`): average score, a first-half-vs-second-half
  trend within the window, high-stress day count, and top triggers.
- 43 new tests - suite grew from 1048 to 1091.

**v1.25.0 - Workout, Meditation, Gratitude, and Meal Summaries**
- New **Workout Summary** (`demo/workout_summary.py`,
  `get_workout_summary`): totals, breakdown by workout type, and a
  consecutive-day workout streak computed over full history rather
  than just the requested window.
- New **Meditation Summary** (`demo/meditation_summary.py`,
  `get_meditation_summary`): totals and a consistency percentage
  (days with at least one session logged).
- New **Gratitude Recap** (`demo/gratitude_recap.py`,
  `get_gratitude_recap`): totals, recurring-word frequency across
  logged items, and the most recent entries.
- New **Meal Summary** (`demo/meal_summary.py`, `get_meal_summary`):
  totals, average calories per meal/day, breakdown by meal time, and
  the most frequently logged foods.
- 43 new tests - suite grew from 1005 to 1048.

**v1.24.0 - Logging Consistency, Time-of-Day Insights, Month-over-Month, Habit PBs**
- New **Logging Consistency** (`demo/consistency.py`,
  `get_logging_consistency`): percentage of recent days with at least
  one entry logged, overall and per tracked metric - unused trackers
  are omitted rather than shown as a discouraging 0%.
- New **Time-of-Day Insights** (`demo/time_of_day.py`,
  `get_time_of_day_insights`): buckets individual logged entries into
  Morning/Afternoon/Evening/Night by hour and reports the best/worst
  time of day per metric - a companion to Day-of-Week Insights that
  works entry-by-entry instead of on daily averages.
- New **Month-over-Month Comparison** (`demo/monthly_summary.py`,
  `get_monthly_comparison`): compares this calendar month so far
  against the same day-count span at the start of last calendar month,
  reusing `compare_periods()`'s averaging/delta math with calendar
  month boundaries instead of rolling day windows; correctly caps a
  longer current month's span against a shorter previous month (e.g.
  comparing a 31-day January against February).
- New **Habit Personal Bests** (`demo/habit_pb.py`,
  `get_habit_pb_progress`): compares every habit's current streak
  against its own personal best - new best, tied, or days remaining to
  tie it - a complement to the fixed-milestone countdown in Habit
  Milestones.
- Also promotes `analytics._extract_metric` to a public `extract_metric`
  (backward-compatible, original kept) so `time_of_day.py` could reuse
  the exact same per-entry metric extraction rather than duplicating
  the per-type rules.
- 54 new tests - suite grew from 951 to 1005.

**v1.23.0 - Day-of-Week Insights, Habit Milestones, Goal Deadlines**
- New **Day-of-Week Insights** (`demo/day_of_week.py`,
  `get_day_of_week_insights`): buckets logged mood/energy/stress/sleep/
  hydration/meeting-hours/readiness by weekday and reports which day
  is best and worst for each metric, purely from data already logged -
  no new tracking, no network call.
- New **Habit Milestones** (`demo/habit_milestones.py`,
  `get_habit_milestones`): counts down every active habit streak to
  its next round-number milestone (7, 14, 30, 50, 100, 150, 200, 365,
  500, 1000 days) in one on-demand list, complementing the existing
  opportunistic near-milestone nudge in `recommendations.py`.
- New **Goal Deadlines** (`demo/goal_deadlines.py`,
  `get_goal_deadlines`): `update_goal` now accepts an optional
  `deadline` (`YYYY-MM-DD`); `get_goal_deadlines` lists every
  deadline-bearing goal sorted by urgency, overdue ones called out
  first with how many days overdue.
- 42 new tests - suite grew from 909 to 951.

**v1.22.0 - Heatmap, Moon Correlation, Sleep Debt, Focus Timer, Markdown Export**
- New **Contribution Heatmap** (`demo/heatmap.py`, `hermes-life-os-heatmap`):
  a GitHub-style SVG calendar heatmap of logging activity - pure SVG,
  no matplotlib, embeddable anywhere.
- New **Moon Phase Correlation** (`demo/moon.py`, `get_moon_correlation`):
  correlates lunar phase against tracked metrics via pure local
  astronomical calculation - zero network calls, unlike weather.py.
- New **Sleep Debt Calculator** (`demo/sleep_debt.py`, `get_sleep_debt`,
  `get_suggested_bedtime`): cumulative shortfall against a target sleep
  duration, plus a bedtime suggestion that pays down debt gradually.
- New **Focus Timer** (`demo/focus_timer.py`, `hermes-life-os-focus`):
  a terminal Pomodoro-style countdown that logs itself on completion
  via the same path a chat-based focus session uses.
- New **Markdown/Obsidian/Notion Export** (`data_export.py --markdown`):
  one daily note per day with YAML frontmatter, matching Obsidian's
  Daily Notes convention and readable by Notion's markdown importer.
- Also promotes `achievements._consecutive_day_streak` to a public
  `consecutive_day_streak` (backward-compatible alias kept) so
  heatmap.py could reuse the exact same streak logic rather than
  duplicating it.
- 75 new tests - suite grew from 834 to 909.

**v1.21.0 - PDF Export, Streak Freezes, On This Day, Daily Prompts**
- **PDF export** for the two biggest reports: `hermes-life-os-review
  --format pdf` renders a two-page, print-friendly PDF version of the
  Life Review (Life Score, retrospective, correlations, achievements,
  habits); `hermes-life-os-wrapped --out card.pdf` picks up PDF
  automatically from the file extension - no new flags needed.
- **Streak freezes**: habits now bank one streak freeze every 7 days of
  an active streak (capped at 3) - `update_habit` with
  `completed=false, use_freeze=true` spends one to protect a streak
  through a missed day instead of resetting it to 0.
- New **On This Day** (`get_on_this_day`): a nostalgia lookup - finds
  memory entries logged on today's month/day in previous years.
- New **Daily Prompt** (`get_daily_prompt`, `demo/prompts.py`): a
  rotating reflection question, deterministic by calendar date - same
  day always returns the same prompt, changes daily, no state to
  persist.
- Also fixes a real Python variable-scoping bug found during testing:
  a local `from storage import get_all_memory` inside one `dispatch_tool`
  branch was shadowing the module-level import for the *entire*
  function, breaking two unrelated tools (`get_correlation_insights`'s
  semantic-recall path and `compare_periods`) whenever `get_on_this_day`
  had been added to the same file. Caught by the full test suite before
  release, not after.
- 62 new tests - suite grew from 806 to 834.

**v1.20.0 - Life Review Report, Household Leaderboard**
- New **Life Review** (`demo/life_review.py`, `hermes-life-os-review`):
  the flagship retrospective report - Life Score trend chart,
  best/toughest day, a period-over-period comparison, every correlation
  detected, achievements earned, and habit streaks, all in one
  self-contained HTML page built for a quarter- or year-long lookback
  window. Reuses the same chart-rendering approach as the dashboard for
  visual consistency.
- New **Leaderboard** (`demo/leaderboard.py`, `join_leaderboard` /
  `leave_leaderboard` / `get_leaderboard` tools): an opt-in, cross-profile
  ranking by average Life Score, logging streak, and achievements
  earned, built on top of the multi-user system. Nobody is included by
  default; opting out takes effect immediately; only those three
  numbers are ever shared across profiles.
- 33 new tests - suite grew from 768 to 805.

**v1.19.0 - Weather Correlation, Quick-Logging Guide**
- New **Weather Correlation** (`demo/weather.py`, `get_weather_correlation`
  tool): fetches historical daily weather via Open-Meteo's free, keyless
  API and correlates temperature/precipitation against tracked metrics
  using the same Pearson approach as the core correlation engine. The
  only tracker that makes a network call - entirely on-demand, sends
  nothing but the place name.
- New [docs/SHORTCUTS.md](docs/SHORTCUTS.md): a step-by-step guide for
  building one-tap Apple Shortcuts, Android (Tasker/HTTP Shortcuts), and
  browser-bookmarklet quick-loggers on top of the existing local REST
  API - no new app, no subscription.
- 20 new tests (all HTTP calls mocked - no real network access
  required to run the suite) - suite grew from 748 to 768.

**v1.18.0 - Reading & Medication Tracking, Recommendations**
- New trackers: **reading/learning** (`log_reading`,
  `get_reading_summary` - sessions, minutes, pages; reading minutes
  feed the correlation engine) and **medication/supplement adherence**
  (`log_medication`, `get_medication_adherence` - taken/skipped dose
  logging with an adherence % per medication).
- New **Recommendations** (`demo/recommendations.py`,
  `get_recommendations` tool): a fully local, rule-based suggestion
  engine combining threshold nudges (low sleep, high stress),
  correlation-derived insights (reusing the existing correlation
  engine), and near-milestone habit streaks into concrete, traceable
  suggestions - no LLM or network call involved.
- 26 new tests - suite grew from 722 to 748.

**v1.17.0 - Spending/Social/Substance Tracking, Life Score, Achievements, Wrapped**
- New trackers alongside nutrition/sleep/fitness/mental: **spending**
  (`log_expense`, `get_spending_summary`), **social connection**
  (`log_social_interaction`, `get_social_summary`), and **substances**
  (`log_substance`, `get_substance_summary` - caffeine, alcohol, or
  anything else). Spending and caffeine feed the correlation engine
  like every other metric.
- New **Life Score** (`demo/life_score.py`, `get_life_score` tool): a
  single 0-100 composite blending whatever's logged that day (mood,
  sleep, hydration, stress, energy, focus) into one at-a-glance
  wellbeing number, with a transparent `components` breakdown - never a
  black box, and never penalized for partial data.
- New **Achievements** (`demo/achievements.py`, `get_achievements`
  tool): streak badges (7/30/100 days, per-habit and overall) and
  count-based milestone badges. Fully read-only and recomputed fresh
  every call - no separate achievements state to fall out of sync with
  your actual logs.
- New **Wrapped** (`demo/wrapped.py`, `hermes-life-os-wrapped`): a
  single shareable PNG summary card (average Life Score, entries
  logged, best day, badges earned) in the spirit of Spotify Wrapped -
  entirely local, no network calls.
- 81 new tests - suite grew from 641 to 722.

**v1.16.0 - Plugin System, Multi-User Accounts, Slack Bot**
- New plugin system (`demo/plugins.py`): drop a `.py` file into
  `~/.hermes/life-os/plugins/` defining `TOOLS` + `dispatch()` and
  Hermes' LLM agent can call it like any built-in tool - no fork, no
  core code changes. A broken plugin is skipped and reported, never
  crashes startup; plugins can't shadow built-in tool names. Ships with
  two ready-to-copy examples (`demo/plugins_examples/`) and a full
  guide at [docs/PLUGINS.md](docs/PLUGINS.md). Also fixes a
  long-standing dead-code bug where `dispatch_tool`'s final "Unknown
  tool" fallback could never actually be reached.
- New multi-user registry (`demo/users.py`): named users, each with
  their own salted-hash API key that resolves to their own profile
  automatically. `hermes-life-os-api` and the new Slack bot are both
  multi-user aware - one running server/bot can now serve a whole
  household or team, each person only ever seeing their own data. Fully
  opt-in; a single `LIFE_OS_API_KEY`/`--profile` keeps working exactly
  as before. See [docs/MULTI_USER.md](docs/MULTI_USER.md).
- New Slack bot (`demo/slack_bot.py`, `hermes-life-os-slack`): the
  fourth chat platform, via Slack's Socket Mode (no public server/
  webhook needed, same as the Telegram bot). Supports both single-user
  (`SLACK_ALLOWED_USER_ID`) and multi-user (linked via `users.py`)
  modes, plus the same photo-based meal logging as the other bots.
- 74 new tests - suite grew from 567 to 641.

**v1.15.0 - Local REST API, Live Web Dashboard, WhatsApp Bot, Predictive Correlations**
- New `hermes-life-os-api` local REST API (`demo/local_api.py`, Flask):
  `GET /api/tools`, `POST /api/tools/<name>`, `GET /api/memory/recent`,
  `GET /api/memory/search` - lets a Shortcut, browser extension, or any
  other client call Hermes' tools over HTTP. Binds to localhost by
  default and requires `LIFE_OS_API_KEY` on every request; refuses to
  start without it.
- New live web dashboard (`demo/web_dashboard.py`,
  `hermes-life-os-web`) - the same charts/correlations/retrospective as
  the static PNG report, but as an always-current local web page that
  refreshes without regenerating a file.
- New WhatsApp bot (`demo/whatsapp_bot.py`, `hermes-life-os-whatsapp`),
  via Twilio's WhatsApp API - the third chat platform alongside
  Telegram and Discord, with the same text/photo-meal-logging feature
  set. Unlike the polling/websocket-based bots, this is a webhook
  server, so every incoming request's Twilio signature is verified
  before processing.
- New lagged/predictive correlations (`compute_lagged_correlations()`
  in `demo/analytics.py`): shifts one metric 1-2 days forward before
  correlating, so results can say "a higher X on one day tends to be
  followed by a higher/lower Y N days later" instead of only reporting
  same-day co-movement. Feeds every existing insight surface (chat,
  `detect_patterns`, both dashboards, the weekly email) plus a new
  dedicated `get_correlation_insights` tool for on-demand deep dives.

**v1.14.0 - Automatic Backups, Photo Meal Logging, Discord Bot, Encryption Re-key**
- Automatic daily local backups of all data, kept on a rolling window,
  restorable via `hermes-life-os-backup`.
- Photo-based meal logging: send the Telegram or Discord bot a photo of
  a meal (with an optional caption) and a vision-capable LLM identifies
  and logs it - no separate step needed.
- New Discord bot (`demo/discord_bot.py`, `hermes-life-os-discord`) -
  the second chat platform alongside Telegram, using discord.py's
  event-driven client rather than a hand-rolled polling loop, so it
  works in a DM or any server channel the bot can see.
- New `hermes-life-os-rekey` tool: safely rotates
  `LIFE_OS_ENCRYPTION_KEY` (decrypts with the old key, rotates the
  salt, re-encrypts with the new one in one step) - also works to
  enable or fully disable encryption after the fact, which simply
  setting a new key directly could not do safely.

**v1.13.0 - Weekly Email Summary, Voice Notes**
- New `hermes-life-os-weekly-email` CLI: emails the same self-contained
  dashboard report (charts, correlations, retrospective, habits) that
  `hermes-life-os-dashboard` generates. Reuses the existing SMTP
  settings (`HERMES_SMTP_*`); new `notifications.send_html_email()`
  sends HTML with a plain-text fallback. Not wired into the scheduler
  by default - schedule it yourself with cron/Task Scheduler if wanted.
- Telegram bot now accepts voice notes: downloaded and transcribed
  locally via a free Whisper model (`faster-whisper`, no cloud API,
  `WHISPER_MODEL` env var to pick model size), then processed exactly
  like a typed message. The reply is prefixed with what Hermes heard,
  and a missing/failed transcription gets a clear message instead of
  silently failing.
- 36 new tests - suite grew from 355 to 391.

**v1.12.0 - Telegram Bot, Semantic Memory Search, Oura Ring Import**
- New `hermes-life-os-telegram` CLI: talk to Hermes from your phone via
  long-polling (no server/webhook needed). Restricted to a single
  `TELEGRAM_CHAT_ID` for privacy. Replies use `run_life_os()`'s new
  `reply_text` field - the model's actual natural-language answer,
  extracted directly rather than parsed from rendered terminal output
  (avoids garbled box-drawing characters and empty-panel replies).
  Long messages auto-split across Telegram's 4096-char limit; failed
  polls back off exponentially (5s -> 5min) instead of hammering the
  API if the token is briefly rate-limited or wrong.
- Hardening: if a weak/small model emits a raw failed tool-call attempt
  as plain text (e.g. `{"name":"recall","parameters":{...}}`) instead of
  actually calling the tool, that's now detected and never relayed to
  the user as if it were a real answer - seen with small local models
  (e.g. `llama3.2:3b`) via Ollama, which can also make unreliable tool
  choices in general; `llama3.1` (8B) or a cloud provider is
  recommended for more consistent behavior.
- New `semantic_recall` chat tool + `semantic_search.py`: meaning-based
  memory search via local (Ollama) or OpenAI embeddings, with a
  per-entry cache that only recomputes when an entry's text actually
  changes. Falls back gracefully with a clear message if no embedding
  provider is reachable.
- New `hermes-life-os-oura` CLI: imports real sleep duration (merges
  directly into the existing "sleep" metric alongside manual logs and
  Apple Health imports) and daily readiness score (`readiness`, a new
  fully tracked metric) from an Oura Ring, via Personal Access Token -
  no OAuth flow needed.
- 83 new tests - suite grew from 272 to 355.

**v1.11.0 - Anomaly Detection, Calendar Import, Proactive Nudges, Data Export, History Queries**
- `check_anomalies` tool + `analytics.detect_anomalies()`: flags statistical
  outlier days (z-score based) in mood/energy/stress/sleep/hydration.
- `compare_before_after` tool + `analytics.compare_before_after()`: compares
  metric averages before vs. after a specific changepoint date (e.g. "did
  starting meditation on March 1st actually help?").
- New `hermes-life-os-calendar` CLI: imports meeting hours per day from a
  standard `.ics` calendar export (Google Calendar/Outlook/Apple Calendar,
  no OAuth needed). `meeting_hours` is now a fully tracked metric -
  participates in correlations, goal-linking, retrospectives, and anomaly
  detection automatically.
- Proactive nudges: the scheduler's new 20:00 `nudge_check` entry
  deterministically (no LLM call) surfaces anomalies and lagging
  metric-linked goals, staying silent when nothing stands out.
- New `hermes-life-os-export` CLI: `--json` for a complete backup, `--csv`
  for a daily summary in the same shape `hermes-life-os-import --csv`
  expects (export, edit, re-import).
- `get_period_summary` tool + `storage.get_memory_by_date_range()`: natural-
  language history queries like "how was I in March?" - the LLM resolves
  the phrase to concrete dates, Hermes returns real averages and notable
  entries for that period.
- 52 new tests - suite grew from 220 to 272.

**v1.10.0 - Goal-Metric Linkage, Retrospective Comparison, Health Data Import**
- Goals can now auto-track from real logged data instead of manual progress
  updates - `update_goal` accepts `metric`/`target`/`direction`/`window_days`;
  new `check_goal_progress` tool recomputes and reports current progress.
- New `compare_periods` tool and a Dashboard "Retrospective" section compare
  this period to the one before it (week-over-week by default,
  `--compare-days` to change the window), color-coded by whether the change
  is favorable per metric.
- New `hermes-life-os-import` CLI: bulk-imports Apple Health `export.xml`
  (Sleep Analysis, Dietary Water) or a generic CSV
  (date + sleep_hours/mood/stress/energy/hydration columns), preserving real
  historical dates instead of stamping everything "today".
- `write_memory()` now only stamps "now" when no timestamp was already
  provided - unchanged for all real-time logging (which never supplies one),
  enables historical-dated bulk import.
- 45 new tests (goal-metric linkage, retrospective comparison, health
  import) - suite grew from 175 to 220.

**v1.9.0 - Multi-Profile, Encryption at Rest, Correcting/Deleting Entries**
- `--profile <name>` (or `LIFE_OS_PROFILE`) isolates all data per person
  under `~/.hermes/life-os/profiles/<name>/` - for shared households.
  Omitting it keeps the original single-profile layout unchanged.
- `LIFE_OS_ENCRYPTION_KEY` - optional encryption at rest (PBKDF2-HMAC-SHA256
  + Fernet/AES) for every data file and every memory.jsonl line. Off by
  default; existing plaintext data reads transparently and gets encrypted
  on next write, no separate migration needed.
- Every memory entry now has a stable id. New `correct_entry` / `delete_entry`
  tools let you fix a mistake or remove a bad log entry through normal
  conversation ("that sleep entry was wrong, it was actually 7 hours" /
  "delete that last entry") instead of it being stuck in an append-only log.
- 39 new tests (12 profiles, 10 encryption, 12 memory edit/delete at the
  storage layer, 5 for the correct_entry/delete_entry chat tools) - suite
  grew from 136 to 175 tests.

**v1.8.0 - PyPI Package, GHCR Image, Contributor Docs**
- `pip install hermes-life-os` - real PyPI packaging via `pyproject.toml`,
  with CLI commands `hermes-life-os`, `hermes-life-os-dashboard`,
  `hermes-life-os-scheduler`. Source layout (`demo/`) unchanged, so
  existing `python demo/demo_life_os.py` usage still works exactly the
  same. Auto-published to PyPI on every GitHub Release.
- `ghcr.io/lethe044/hermes-life-os` - pre-built Docker image, auto-published
  on every push to `main` and every release. No `git clone` needed to try it.
- Example dashboard chart embedded in the README (see the
  [Dashboard](#dashboard) section).
- `CONTRIBUTING.md` and GitHub issue templates (bug report / feature
  request) for contributors.

**v1.7.0 - CI, Docker & Dashboard**
- GitHub Actions workflow runs the full test suite on every push/PR
  across Python 3.10/3.11/3.12, with a status badge in this README
- `Dockerfile` + `docker-compose.yml` for a zero-install trial - pairs
  with a local Ollama container for a completely free, no-API-key run
- New `demo/dashboard.py`: generates a self-contained HTML report with
  charts of your mood/sleep/stress/energy/hydration trends and the
  correlations Hermes detects - pure local data analysis, no LLM call
- 7 new tests for the dashboard - suite grew from 129 to 136 tests

**v1.6.0 - Multi-Provider LLM Support**
- New `demo/llm_providers.py`: provider-agnostic client layer supporting
  Ollama (free, fully local, no API key), OpenAI, Anthropic, and
  OpenRouter, with auto-detection from whichever key is set
- `--provider` flag / `LIFE_OS_PROVIDER` env var to force a specific backend
- Friendly troubleshooting output on connection/auth failures instead of
  raw tracebacks
- 16 new unit tests (`test_llm_providers.py`) covering provider resolution
  and the Anthropic <-> OpenAI message/tool format adapter - total suite
  grew from 113 to 129 tests, all passing

**v1.5.0 - Modular Architecture, Scheduler & Notifications**
- Split the ~1600-line `demo_life_os.py` monolith into focused, independently
  testable modules: `storage.py`, `patterns.py`, `tools.py` (demo_life_os.py
  is now the CLI/chat/voice orchestration layer only)
- New `demo/scheduler.py`: dependency-free cron-style engine implementing
  the Daily Rhythm table (07:00 morning, 12:00 midday, 18:00 evening,
  Monday 08:00 weekly), with pure, fully unit-tested scheduling logic
- New `demo/notifications.py`: pluggable delivery via console, webhook,
  Telegram, or email (SMTP) - stdlib only, never crashes on missing config
- New `demo/run_scheduler.py`: production entry point wiring the scheduler
  to real briefing generation and delivery
- 77 new unit tests (`test_storage.py`, `test_tools.py`, `test_scheduler.py`,
  `test_notifications.py`) - total suite grew from 36 to 113 tests, all passing

**v1.4.0 - Real Correlation Engine**
- New `demo/analytics.py` module: pure-stdlib Pearson correlation analysis
  across mood, sleep, stress, energy, and hydration
- `detect_patterns()` now computes actual daily-aggregated correlations
  (r-value, day count, direction, strength) instead of a static placeholder
  message ("correlation analysis active")
- Correlation insights are surfaced automatically in `detect_patterns`
  tool output, feeding into morning/evening/weekly briefings
- 14 new unit tests covering the correlation engine (`tests/test_analytics.py`)

**v1.3.0 - Dream Journal**
- Dream logging mode with symbol, emotion, tone and vividness tracking
- Sleep/mood/stress/dream correlation detection
- Recurring symbol pattern detection across 30 days
- Morning briefing includes dream analysis

**v1.2.0 - Voice & Performance**
- Voice mode - speak to Hermes, hear responses via system TTS
- Concurrent tool execution - read-only tools run in parallel threads
- Microphone input via SpeechRecognition

**v1.1.0 - Health & Wellness Expansion**
- Nutrition, sleep, hydration, fitness, mental, focus tracking
- Full health dashboard and weekly health report
- Interactive chat mode

**v1.0.0 - Initial Release**
- 12 demo modes covering every life dimension
- Pattern detection across mood, sleep, nutrition, stress, focus
- Memory-driven briefings, Atropos RL environment
