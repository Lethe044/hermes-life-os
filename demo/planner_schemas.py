"""
Hermes Life OS - tool schemas for the planner modules
=======================================================
Pure data: the schemas of the tools that live in tasks.py, body.py,
subscriptions.py, people.py, agenda.py, lists.py, savings.py,
symptoms.py, notes.py, income.py, debts.py, countdowns.py,
supplies.py, timeblocks.py, okrs.py, recipes.py, trips.py, finder.py, closing.py,
repair_hints.py, chores.py, expiries.py, routines.py, gifts.py, decisions.py and weekahead.py, plus the tool name -> module map
tools.py uses to dispatch them. Kept apart from those modules so that
importing tools.py never imports (and never binds to) the storage layer of
modules that only matter when one of their tools is actually called.
"""

from __future__ import annotations

from typing import Any, Dict, List

# The `date` property of every tool that can log for a past day (tools.py uses the same text).
ENTRY_DATE_PROP = {
    "type": "string",
    "description": "Optional. The day this happened as YYYY-MM-DD, to log something afterwards "
                   "(e.g. yesterday's lunch). Defaults to today. Future dates and dates more than "
                   "365 days back are rejected.",
}


def _tool(name: str, description: str, properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required}}}


_TASK_REF = {"type": "string", "description": "The task's id (from list_tasks) or some words from its text."}

TASK_SCHEMAS = [
    _tool("add_task", "Add a to-do. Due can be YYYY-MM-DD, today, tomorrow, in 3 days or a weekday name. "
                      "A repeating task (daily, weekdays, weekly, monthly) creates its next occurrence when completed.",
          {"text": {"type": "string"},
           "due": {"type": "string", "description": "Optional due date."},
           "priority": {"type": "string", "enum": ["high", "normal", "low"]},
           "tags": {"type": "array", "items": {"type": "string"}},
           "repeat": {"type": "string", "enum": ["daily", "weekdays", "weekly", "monthly"]},
           "notes": {"type": "string"}}, ["text"]),
    _tool("list_tasks", "List to-dos, most urgent first (overdue, then by due date and priority).",
          {"status": {"type": "string", "enum": ["open", "done", "all"], "description": "Default open."},
           "tag": {"type": "string"},
           "due_within": {"type": "integer", "description": "Only open tasks due within this many days (overdue included)."},
           "limit": {"type": "integer", "description": "Default 30, at most 200."}}, []),
    _tool("complete_task", "Mark a to-do done (by id or words from its text).", {"task": _TASK_REF}, ["task"]),
    _tool("update_task", "Change a to-do: text, due ('' clears), priority, tags, repeat ('' clears), notes, "
                         "or done=false to reopen it.",
          {"task": _TASK_REF, "fields": {"type": "object", "description": "Only the fields to change."}},
          ["task", "fields"]),
    _tool("delete_task", "Delete a to-do.", {"task": _TASK_REF}, ["task"]),
    _tool("get_task_summary", "Counts of open, overdue, due today and due this week tasks, and how many "
                              "were finished recently.", {}, []),
    _tool("clear_done_tasks", "Delete finished to-dos (all, or only those finished more than N days ago).",
          {"older_than_days": {"type": "integer", "description": "Default 0 = all finished tasks."}}, []),
]

BODY_SCHEMAS = [
    _tool("log_body_metric", "Log a body measurement: weight, body_fat, waist, hips, resting_hr, blood_pressure "
                             "(value = systolic, diastolic = the bottom number), blood_glucose, temperature, spo2. "
                             "Units such as lb, in, mmol/L or F are converted for analysis.",
          {"metric": {"type": "string", "enum": ["weight", "body_fat", "waist", "hips", "resting_hr",
                                                 "blood_pressure", "blood_glucose", "temperature", "spo2"]},
           "value": {"type": "number"},
           "unit": {"type": "string", "description": "Optional, e.g. lb, kg, in, cm, mmol/L, F."},
           "diastolic": {"type": "number", "description": "Blood pressure only."},
           "notes": {"type": "string"},
           "date": dict(ENTRY_DATE_PROP)}, ["metric", "value"]),
    _tool("get_body_trend", "Trend of a body metric over recent days (latest, average, range, change, rate per "
                            "week, progress to a target). With no metric, shows the latest reading of each.",
          {"metric": {"type": "string"}, "days": {"type": "integer", "description": "Default 30."}}, []),
    _tool("set_body_goal", "Set (or clear) a target for a body metric, e.g. weight 75 kg. Progress and an estimated "
                           "date are shown by get_body_trend.",
          {"metric": {"type": "string"}, "target": {"type": "number"}, "unit": {"type": "string"},
           "clear": {"type": "boolean", "description": "true removes the target."}}, ["metric"]),
]

_SUB_REF = {"type": "string", "description": "The subscription's id or name."}

SUBSCRIPTION_SCHEMAS = [
    _tool("add_subscription", "Track a recurring payment (streaming, gym, insurance...). next_date defaults to one "
                              "cycle from today.",
          {"name": {"type": "string"}, "amount": {"type": "number"},
           "cycle": {"type": "string", "enum": ["weekly", "monthly", "quarterly", "yearly"]},
           "next_date": {"type": "string", "description": "Next renewal, YYYY-MM-DD."},
           "category": {"type": "string"}, "notes": {"type": "string"}}, ["name", "amount"]),
    _tool("list_subscriptions", "List subscriptions with their monthly cost and next renewal.",
          {"include_cancelled": {"type": "boolean"}}, []),
    _tool("update_subscription", "Change a subscription: name, amount, cycle, next_date, category, notes.",
          {"subscription": _SUB_REF, "fields": {"type": "object"}}, ["subscription", "fields"]),
    _tool("cancel_subscription", "Mark a subscription cancelled (kept for history, dropped from totals).",
          {"subscription": _SUB_REF}, ["subscription"]),
    _tool("resume_subscription", "Reactivate a cancelled subscription.",
          {"subscription": _SUB_REF, "next_date": {"type": "string"}}, ["subscription"]),
    _tool("delete_subscription", "Delete a subscription entirely.", {"subscription": _SUB_REF}, ["subscription"]),
    _tool("get_subscription_summary", "Total subscription cost per month and per year, by category, the biggest "
                                      "ones, and renewals coming up.",
          {"days": {"type": "integer", "description": "Renewal window, default 14."}}, []),
    _tool("pay_subscription", "Record that a subscription was just paid: logs an expense in its category and moves "
                              "the next renewal one cycle on.",
          {"subscription": _SUB_REF,
           "log_expense": {"type": "boolean", "description": "Default true. false only moves the date."}},
          ["subscription"]),
]

_PERSON_REF = {"type": "string", "description": "The person's name (or part of it) or id."}

PEOPLE_SCHEMAS = [
    _tool("add_person", "Save someone you want to stay in touch with: optional birthday (MM-DD or YYYY-MM-DD) and "
                        "how often to be in touch (days).",
          {"name": {"type": "string"}, "birthday": {"type": "string"},
           "keep_in_touch_days": {"type": "integer"}, "notes": {"type": "string"}}, ["name"]),
    _tool("list_people", "List saved people with last contact and upcoming birthdays.", {}, []),
    _tool("get_person", "Details and recent contact history of one person.", {"person": _PERSON_REF}, ["person"]),
    _tool("update_person", "Change a person: name, birthday ('' clears), keep_in_touch_days (0 clears), notes.",
          {"person": _PERSON_REF, "fields": {"type": "object"}}, ["person", "fields"]),
    _tool("delete_person", "Remove a person and their contact history.", {"person": _PERSON_REF}, ["person"]),
    _tool("log_contact", "Record that you were in touch with someone (call, message, visit).",
          {"person": _PERSON_REF, "date": {"type": "string", "description": "YYYY-MM-DD, default today."},
           "note": {"type": "string"}}, ["person"]),
    _tool("get_people_due", "Who you are overdue to contact, and birthdays coming up.",
          {"days": {"type": "integer", "description": "Birthday window, default 30."}}, []),
]

AGENDA_SCHEMAS = [
    _tool("get_today_agenda", "Everything that needs attention today in one place: tasks due or overdue, "
                              "reminders, subscription renewals, birthdays and overdue contacts, habit streaks "
                              "that need a check-in, and budget alerts. Use for 'what do I have today?' or "
                              "'plan my day'.", {}, []),
]

_LIST_PROP = {"type": "string", "description": "List name, default 'shopping'."}
_ITEM_REF = {"type": "string", "description": "An item's id or some words from its text."}
_ITEMS_REF = {"type": "array", "items": {"type": "string"}, "description": "Several item names or ids."}

LIST_SCHEMAS = [
    _tool("add_list_items", "Add one or more items to a named checklist (default 'shopping'): items can be a "
                            "comma-separated text or a list. Items already open on the list are skipped.",
          {"items": {"type": "array", "items": {"type": "string"},
                     "description": "Items to add (a comma-separated string also works)."},
           "list": _LIST_PROP,
           "quantity": {"type": "string", "description": "Only when adding a single item, e.g. '2 kg'."}},
          ["items"]),
    _tool("get_list", "Show one checklist: what is still to get and what is ticked.", {"list": _LIST_PROP}, []),
    _tool("get_lists", "Overview of all checklists with their open and ticked counts.", {}, []),
    _tool("check_list_item", "Tick off (or untick with checked=false) one or more list items.",
          {"item": _ITEM_REF, "items": _ITEMS_REF, "list": _LIST_PROP,
           "checked": {"type": "boolean", "description": "Default true."}}, []),
    _tool("remove_list_items", "Remove one or more items from a list.",
          {"item": _ITEM_REF, "items": _ITEMS_REF, "list": _LIST_PROP}, []),
    _tool("clear_checked_items", "Remove all ticked items from a list (or from every list if none is named).",
          {"list": {"type": "string"}}, []),
    _tool("delete_list", "Delete a whole checklist with all its items.", {"list": {"type": "string"}}, ["list"]),
]

_GOAL_REF = {"type": "string", "description": "The savings goal's name (or part of it) or id."}

SAVINGS_SCHEMAS = [
    _tool("add_savings_goal", "Start a savings goal with a target amount and an optional deadline and starting "
                              "balance. Amounts have no currency.",
          {"name": {"type": "string"}, "target": {"type": "number"},
           "deadline": {"type": "string", "description": "Optional, YYYY-MM-DD."},
           "saved": {"type": "number", "description": "Optional amount already saved."},
           "notes": {"type": "string"}}, ["name", "target"]),
    _tool("contribute_to_savings", "Add money to a savings goal, or take some out with a negative amount.",
          {"goal": _GOAL_REF, "amount": {"type": "number"}, "note": {"type": "string"},
           "date": {"type": "string", "description": "YYYY-MM-DD, default today. Not in the future."}}, ["goal", "amount"]),
    _tool("get_savings", "Progress of all savings goals, or one in detail (pace, estimated finish, what to put "
                         "aside per month to meet the deadline).", {"goal": _GOAL_REF}, []),
    _tool("update_savings_goal", "Change a savings goal: name, target, deadline ('' clears) or notes.",
          {"goal": _GOAL_REF, "fields": {"type": "object"}}, ["goal", "fields"]),
    _tool("delete_savings_goal", "Delete a savings goal and its history.", {"goal": _GOAL_REF}, ["goal"]),
]

SYMPTOM_SCHEMAS = [
    _tool("log_symptom", "Log a recurring symptom such as a headache, back pain or heartburn with a severity "
                         "from 1 to 10, optional duration, suspected triggers and notes. A personal log, not a "
                         "diagnosis.",
          {"symptom": {"type": "string"}, "severity": {"type": "integer", "description": "1 (mild) to 10 (worst)."},
           "duration_minutes": {"type": "integer"},
           "triggers": {"type": "array", "items": {"type": "string"},
                        "description": "Suspected triggers, e.g. stress, coffee, bad sleep."},
           "time": {"type": "string", "description": "Optional HH:MM."}, "notes": {"type": "string"},
           "date": dict(ENTRY_DATE_PROP)}, ["symptom", "severity"]),
    _tool("get_symptom_summary", "How often and how badly symptoms occurred: counts, average severity, days since "
                                 "the last one, common triggers, trend, worst weekday and sleep before symptom days.",
          {"days": {"type": "integer", "description": "Window, 1-365, default 30."},
           "symptom": {"type": "string", "description": "Only this symptom."}}, []),
    _tool("get_symptom_triggers", "Compare the days a symptom happened with the days it did not, using what was "
                                  "logged elsewhere: the sleep and stress before it, water, caffeine, alcohol, "
                                  "workouts and the weekday, and how often each suspected trigger you named came "
                                  "up. Shows patterns in your own data, not causes or medical advice.",
          {"symptom": {"type": "string", "description": "The symptom, e.g. migraine. Default: the most frequent."},
           "days": {"type": "integer", "description": "Window, 14-365, default 90."}}, []),
]

_NOTE_REF = {"type": "string", "description": "The note's id or some words from its text."}

NOTE_SCHEMAS = [
    _tool("add_note", "Save a quick note or idea with optional tags, and optionally pin it.",
          {"text": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}},
           "pinned": {"type": "boolean"}}, ["text"]),
    _tool("list_notes", "List notes, pinned first then newest, optionally for one tag or only pinned ones.",
          {"tag": {"type": "string"}, "pinned": {"type": "boolean"},
           "limit": {"type": "integer", "description": "Default 20, at most 100."}}, []),
    _tool("search_notes", "Find notes containing all the given words in their text or tags.",
          {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    _tool("update_note", "Change a note: text, tags or pinned.",
          {"note": _NOTE_REF, "fields": {"type": "object"}}, ["note", "fields"]),
    _tool("delete_note", "Delete a note.", {"note": _NOTE_REF}, ["note"]),
]

INCOME_SCHEMAS = [
    _tool("log_income", "Log money coming in (salary, refund, side job). Amounts have no currency. Mirrors "
                        "log_expense; can be backdated.",
          {"amount": {"type": "number"}, "source": {"type": "string", "description": "e.g. salary, freelance."},
           "notes": {"type": "string"}, "date": dict(ENTRY_DATE_PROP)}, ["amount"]),
    _tool("get_cash_flow", "Income vs spending per month: net, share of income kept (savings rate), average "
                           "net and income sources.",
          {"months": {"type": "integer", "description": "Calendar months including this one, 1-24, default 3."}}, []),
]

_DEBT_REF = {"type": "string", "description": "The debt's id or the other person's name."}

DEBT_SCHEMAS = [
    _tool("add_debt", "Record money you owe someone (direction 'owe') or that someone owes you (direction 'owed').",
          {"who": {"type": "string"}, "amount": {"type": "number"},
           "direction": {"type": "string", "enum": ["owe", "owed"],
                         "description": "'owe' = you owe them, 'owed' = they owe you."},
           "due": {"type": "string", "description": "Optional, YYYY-MM-DD."}, "notes": {"type": "string"}},
          ["who", "amount", "direction"]),
    _tool("record_debt_payment", "Record a (partial) payment on a debt. Cannot exceed what is still open.",
          {"debt": _DEBT_REF, "amount": {"type": "number"}, "note": {"type": "string"},
           "date": {"type": "string", "description": "YYYY-MM-DD, default today. Not in the future."}},
          ["debt", "amount"]),
    _tool("get_debts", "What you owe and what you are owed, with due dates and overdue flags.",
          {"include_settled": {"type": "boolean", "description": "Also show fully paid debts. Default false."}}, []),
    _tool("update_debt", "Change a debt: who, amount, due ('' clears) or notes.",
          {"debt": _DEBT_REF, "fields": {"type": "object"}}, ["debt", "fields"]),
    _tool("delete_debt", "Delete a debt and its payments.", {"debt": _DEBT_REF}, ["debt"]),
]

_COUNTDOWN_REF = {"type": "string", "description": "The countdown's name (or part of it) or id."}

COUNTDOWN_SCHEMAS = [
    _tool("add_countdown", "Count the days until (or since) an event, e.g. a holiday, an exam or quitting "
                           "something. A yearly countdown always points at its next anniversary.",
          {"name": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD, past dates allowed."},
           "repeat": {"type": "string", "enum": ["yearly"]}, "notes": {"type": "string"}}, ["name", "date"]),
    _tool("get_countdowns", "All countdowns: upcoming first, then days since for past ones.",
          {"include_past": {"type": "boolean", "description": "Default true."}}, []),
    _tool("update_countdown", "Change a countdown: name, date, repeat ('' clears) or notes.",
          {"countdown": _COUNTDOWN_REF, "fields": {"type": "object"}}, ["countdown", "fields"]),
    _tool("delete_countdown", "Delete a countdown.", {"countdown": _COUNTDOWN_REF}, ["countdown"]),
]

_SUPPLY_REF = {"type": "string", "description": "The supply's name (or part of it) or id."}

SUPPLY_SCHEMAS = [
    _tool("add_supply", "Track something that runs out (pills, contact lenses, pet food): how many you have and "
                        "how many you use per day. Hermes works out how many are left and when it runs out.",
          {"name": {"type": "string"}, "quantity": {"type": "number", "description": "How many you have."},
           "per_day": {"type": "number", "description": "How many you use per day."},
           "unit": {"type": "string", "description": "e.g. pills."},
           "as_of": {"type": "string", "description": "Day of the count, YYYY-MM-DD, default today."},
           "notes": {"type": "string"}}, ["name", "quantity", "per_day"]),
    _tool("refill_supply", "Record a refill: adds to what is left (mode 'add', default) or sets the count today "
                           "(mode 'set').",
          {"supply": _SUPPLY_REF, "quantity": {"type": "number"},
           "mode": {"type": "string", "enum": ["add", "set"]}}, ["supply", "quantity"]),
    _tool("get_supplies", "How many of each supply are left and when each runs out, soonest first.", {}, []),
    _tool("update_supply", "Change a supply: name, per_day, unit or notes (use refill_supply for the count).",
          {"supply": _SUPPLY_REF, "fields": {"type": "object"}}, ["supply", "fields"]),
    _tool("delete_supply", "Stop tracking a supply.", {"supply": _SUPPLY_REF}, ["supply"]),
]

_BLOCK_REF = {"type": "string", "description": "The block's id or some words from its title."}
_BLOCK_DATE = {"type": "string", "description": "Optional day (YYYY-MM-DD, today, tomorrow or a weekday) to narrow "
                                                 "down a title that repeats on several days."}

TIMEBLOCK_SCHEMAS = [
    _tool("add_time_block", "Plan a block of time in a day (for example deep work 09:00-10:30). Blocks on one day "
                            "cannot overlap. Give an end time or duration_minutes. A task can be linked, which "
                            "also supplies the title.",
          {"title": {"type": "string"}, "start": {"type": "string", "description": "HH:MM or 2:30pm."},
           "end": {"type": "string", "description": "HH:MM (24:00 allowed)."},
           "duration_minutes": {"type": "integer", "description": "Instead of end, 5 to 960."},
           "date": {"type": "string", "description": "YYYY-MM-DD, today, tomorrow, in 3 days or a weekday; default today."},
           "category": {"type": "string", "description": "e.g. work, study, exercise. Default general."},
           "task": {"type": "string", "description": "Optional open task (id or words) to link."},
           "notes": {"type": "string"}}, ["start"]),
    _tool("get_day_plan", "The plan of one day in time order with the free gaps between blocks, how much is planned "
                          "and done, and what is happening now or next.",
          {"date": {"type": "string", "description": "Default today."}}, []),
    _tool("update_time_block", "Change a block: title, date, start, end, category, notes or done.",
          {"block": _BLOCK_REF, "fields": {"type": "object", "description": "Only the fields to change."},
           "date": _BLOCK_DATE}, ["block", "fields"]),
    _tool("delete_time_block", "Delete a time block.", {"block": _BLOCK_REF, "date": _BLOCK_DATE}, ["block"]),
    _tool("finish_time_block", "Mark a block done, and optionally complete the task it is linked to.",
          {"block": _BLOCK_REF, "complete_task": {"type": "boolean"}, "date": _BLOCK_DATE}, ["block"]),
    _tool("find_free_time", "Find free slots of a given length between 07:00 and 22:00 (up to five, soonest first), "
                            "today onwards or on a given day, optionally over several days.",
          {"duration_minutes": {"type": "integer"}, "date": {"type": "string", "description": "First day, default today."},
           "days": {"type": "integer", "description": "How many days to search, 1-14, default 1."},
           "earliest": {"type": "string", "description": "HH:MM, default 07:00."},
           "latest": {"type": "string", "description": "HH:MM, default 22:00."}}, ["duration_minutes"]),
    _tool("schedule_task", "Put an open task into the first free slot (on a given day, or in the next 7 days) as a "
                           "time block linked to the task.",
          {"task": {"type": "string", "description": "The task's id or some words from its text."},
           "duration_minutes": {"type": "integer", "description": "Default 60."},
           "date": {"type": "string", "description": "Only this day; default: the next 7 days."},
           "earliest": {"type": "string"}, "latest": {"type": "string"}, "category": {"type": "string"}}, ["task"]),
    _tool("get_time_allocation", "Where the planned time went over the last days: hours per category, how much of it "
                                 "was marked done.",
          {"days": {"type": "integer", "description": "1-90, default 7."}}, []),
]

_OBJECTIVE_REF = {"type": "string", "description": "The objective's id or some words from its name."}
_KR_REF = {"type": "string", "description": "The key result's id or some words from its name."}

OKR_SCHEMAS = [
    _tool("add_objective", "Set an objective for a period with measurable key results, e.g. 'Get fit' for this "
                           "quarter with 'run 100 km' and 'weight 85 -> 80'. Progress is compared with the time "
                           "that has passed.",
          {"name": {"type": "string"},
           "period": {"type": "string", "description": "week, month, quarter (default), year, 2026-Q4, 2026-10 or 2026."},
           "start": {"type": "string", "description": "YYYY-MM-DD, instead of period (needs end)."},
           "end": {"type": "string", "description": "YYYY-MM-DD."}, "notes": {"type": "string"},
           "key_results": {"type": "array", "description": "Up to 8: {name, target, start_value, unit}.",
                           "items": {"type": "object", "properties": {
                               "name": {"type": "string"}, "target": {"type": "number"},
                               "start_value": {"type": "number", "description": "Default 0."},
                               "unit": {"type": "string"}}, "required": ["name", "target"]}}}, ["name"]),
    _tool("add_key_result", "Add a measurable key result to an objective (a target below the start means 'go down').",
          {"objective": _OBJECTIVE_REF, "name": {"type": "string"}, "target": {"type": "number"},
           "start_value": {"type": "number", "description": "Default 0."}, "unit": {"type": "string"}},
          ["objective", "name", "target"]),
    _tool("record_key_result", "Record progress on a key result: the new total (value) or the change (add, may be "
                               "negative). The key result may be left out when the objective has only one.",
          {"objective": _OBJECTIVE_REF, "key_result": _KR_REF, "value": {"type": "number"},
           "add": {"type": "number"}}, ["objective"]),
    _tool("get_okrs", "Objectives with progress, expected progress and whether you are on track. With an objective, "
                      "its key results and their history.",
          {"status": {"type": "string", "enum": ["active", "done", "dropped", "all"], "description": "Default active."},
           "objective": _OBJECTIVE_REF}, []),
    _tool("update_okr", "Change an objective (name, notes, start, end, status active/done/dropped) or, with "
                        "key_result, one of its key results (name, target, start_value, unit, current).",
          {"objective": _OBJECTIVE_REF, "key_result": _KR_REF, "fields": {"type": "object"}}, ["objective", "fields"]),
    _tool("delete_okr", "Delete an objective with its key results, or only one key result.",
          {"objective": _OBJECTIVE_REF, "key_result": _KR_REF}, ["objective"]),
]

_RECIPE_REF = {"type": "string", "description": "The recipe's id or some words from its name."}
_SLOT = {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]}

RECIPE_SCHEMAS = [
    _tool("add_recipe", "Save a recipe: ingredients like '200 g flour' or '2 eggs', steps, servings, tags, calories "
                        "per serving and minutes.",
          {"name": {"type": "string"},
           "ingredients": {"type": "array", "items": {"type": "string"},
                           "description": "e.g. ['200 g flour', '2 eggs', 'salt'] (or objects {name, quantity, unit})."},
           "steps": {"type": "array", "items": {"type": "string"}},
           "servings": {"type": "integer", "description": "How many it makes, default 2."},
           "tags": {"type": "array", "items": {"type": "string"}},
           "calories_per_serving": {"type": "integer"}, "minutes": {"type": "integer"}, "notes": {"type": "string"}},
          ["name", "ingredients"]),
    _tool("get_recipes", "List recipes, optionally for one tag or words in the name or ingredients.",
          {"tag": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer"}}, []),
    _tool("get_recipe", "Show a recipe, optionally scaled to a number of servings.",
          {"recipe": _RECIPE_REF, "servings": {"type": "integer"}}, ["recipe"]),
    _tool("update_recipe", "Change a recipe: name, servings, ingredients (replaces them), steps, tags, calories, "
                           "minutes or notes.",
          {"recipe": _RECIPE_REF, "fields": {"type": "object"}}, ["recipe", "fields"]),
    _tool("delete_recipe", "Delete a recipe (planned meals that used it stay as plain text).",
          {"recipe": _RECIPE_REF}, ["recipe"]),
    _tool("suggest_recipes", "Suggest what to cook next: recipes never cooked or cooked longest ago, optionally for "
                             "one tag or within a time limit.",
          {"tag": {"type": "string"}, "max_minutes": {"type": "integer"}, "limit": {"type": "integer"}}, []),
    _tool("plan_meal", "Plan a meal for a slot of a day: a recipe or plain text such as 'leftovers', optionally "
                       "repeated on following days (meal prep).",
          {"slot": _SLOT, "date": {"type": "string", "description": "YYYY-MM-DD, today, tomorrow or a weekday; default today."},
           "recipe": _RECIPE_REF, "text": {"type": "string", "description": "Instead of a recipe."},
           "servings": {"type": "integer", "description": "Default: the recipe's servings."},
           "repeat_days": {"type": "integer", "description": "Plan it on this many consecutive days, 1-14."}},
          ["slot"]),
    _tool("get_meal_plan", "The meal plan for the coming days, with calories where known.",
          {"date": {"type": "string", "description": "First day, default today."},
           "days": {"type": "integer", "description": "1-31, default 7."}}, []),
    _tool("clear_meals", "Remove planned meals: one by id, or every meal of a day (optionally one slot).",
          {"meal": {"type": "string", "description": "A planned meal's id."},
           "date": {"type": "string"}, "slot": _SLOT}, []),
    _tool("log_planned_meal", "Log a planned meal as eaten in the nutrition log (and count its recipe as cooked). "
                              "Only for meals of today or earlier.",
          {"meal": {"type": "string", "description": "The planned meal's id or words from its name or slot."},
           "date": {"type": "string", "description": "The day of the meal, default today."},
           "portions": {"type": "number", "description": "How many servings YOU ate, default 1 (0.25 to 20)."}},
          ["meal"]),
    _tool("shopping_from_plan", "Add everything the planned recipes need to a list (default: shopping). Quantities "
                                "are added up and scaled to the planned servings; items already on the list stay as "
                                "they are.",
          {"date": {"type": "string", "description": "First day, default today."},
           "days": {"type": "integer", "description": "1-31, default 7."},
           "list": {"type": "string", "description": "List name, default 'shopping'."},
           "include_eaten": {"type": "boolean"},
           "skip": {"type": "array", "items": {"type": "string"},
                    "description": "Ingredients you already have, e.g. salt, water."}}, []),
]

_TRIP_REF = {"type": "string", "description": "The trip's id or some words from its name or destination."}

TRIP_SCHEMAS = [
    _tool("add_trip", "Plan a trip with dates, destination, an optional budget and a packing list that can start "
                      "from templates (basic, documents, flight, city, beach, hiking, winter, business).",
          {"name": {"type": "string"}, "start": {"type": "string", "description": "YYYY-MM-DD, tomorrow, in 3 weeks or a weekday."},
           "end": {"type": "string", "description": "Last day; default: a one-day trip."},
           "destination": {"type": "string"}, "budget": {"type": "number"}, "notes": {"type": "string"},
           "template": {"type": "array", "items": {"type": "string"}, "description": "Packing templates to start from."}},
          ["name", "start"]),
    _tool("get_trips", "Ongoing and upcoming trips with the countdown and packing progress.",
          {"include_past": {"type": "boolean"}}, []),
    _tool("get_trip", "One trip in full: dates, budget per day, what is still to pack and the itinerary.",
          {"trip": _TRIP_REF}, ["trip"]),
    _tool("update_trip", "Change a trip: name, destination, start, end, budget ('' clears) or notes.",
          {"trip": _TRIP_REF, "fields": {"type": "object"}}, ["trip", "fields"]),
    _tool("delete_trip", "Delete a trip with its packing list and itinerary.", {"trip": _TRIP_REF}, ["trip"]),
    _tool("add_packing_items", "Add items to a trip's packing list: your own and/or a template.",
          {"trip": _TRIP_REF, "items": {"type": "array", "items": {"type": "string"}},
           "template": {"type": "array", "items": {"type": "string"},
                        "description": "basic, documents, flight, city, beach, hiking, winter, business."}}, ["trip"]),
    _tool("pack_items", "Tick items as packed (or untick with packed=false), by id or words; 'all' for every item.",
          {"trip": _TRIP_REF, "items": {"type": "array", "items": {"type": "string"}},
           "packed": {"type": "boolean", "description": "Default true."}}, ["trip", "items"]),
    _tool("remove_packing_items", "Remove items from a trip's packing list ('all' for every item).",
          {"trip": _TRIP_REF, "items": {"type": "array", "items": {"type": "string"}}}, ["trip", "items"]),
    _tool("add_itinerary_item", "Add something to a trip's day-by-day plan (a flight, a booking, a visit).",
          {"trip": _TRIP_REF, "text": {"type": "string"}, "date": {"type": "string", "description": "A day of the trip."},
           "time": {"type": "string", "description": "Optional HH:MM."}}, ["trip", "text", "date"]),
    _tool("remove_itinerary_item", "Remove an itinerary item (its id or words from its text).",
          {"trip": _TRIP_REF, "item": {"type": "string"}}, ["trip", "item"]),
]

_CHORE_REF = {"type": "string", "description": "The chore's name (or part of it) or id."}

CHORE_SCHEMAS = [
    _tool("add_chore", "Add something that repeats on a schedule: watering plants, changing a filter, a car service. "
                       "The next due date counts from the day it was last done.",
          {"name": {"type": "string"},
           "every": {"type": "string", "description": "daily, weekly, biweekly, monthly, quarterly, yearly, 'every 10 days', "
                                                       "'every 3 months' (a number alone means days)."},
           "start": {"type": "string", "description": "First due date, default today. YYYY-MM-DD, tomorrow, in 3 days or a weekday."},
           "notes": {"type": "string"}}, ["name", "every"]),
    _tool("complete_chore", "Mark a chore done (today unless a date is given); the next one is due one interval later.",
          {"chore": _CHORE_REF, "date": {"type": "string", "description": "YYYY-MM-DD, yesterday or today. Not in the future."}},
          ["chore"]),
    _tool("get_chores", "Chores with their next due date, overdue ones first.",
          {"filter": {"type": "string", "enum": ["all", "due"], "description": "due = overdue or due within 7 days."}}, []),
    _tool("update_chore", "Change a chore: name, every, start, last_done ('' clears) or notes.",
          {"chore": _CHORE_REF, "fields": {"type": "object"}}, ["chore", "fields"]),
    _tool("delete_chore", "Delete a chore.", {"chore": _CHORE_REF}, ["chore"]),
]

_EXPIRY_REF = {"type": "string", "description": "The item's name (or part of it) or id."}

EXPIRY_SCHEMAS = [
    _tool("add_expiry", "Track something that expires on a date (passport, driving licence, insurance, warranty, "
                        "membership) so you are reminded in time.",
          {"name": {"type": "string"}, "date": {"type": "string", "description": "Last valid day, YYYY-MM-DD."},
           "remind_days": {"type": "integer", "description": "Start reminding this many days before, 1-365, default 30."},
           "category": {"type": "string", "enum": ["document", "insurance", "license", "warranty", "membership", "other"]},
           "notes": {"type": "string"}}, ["name", "date"]),
    _tool("get_expiries", "Everything with an expiry date, earliest first, with what is expired or expiring soon.",
          {"filter": {"type": "string", "enum": ["all", "soon"], "description": "soon = expired or inside its reminder window."}}, []),
    _tool("renew_expiry", "Record a renewal: give the new expiry date, or a number of months to add to the current one "
                          "(counted from today when it already expired).",
          {"item": _EXPIRY_REF, "new_date": {"type": "string", "description": "YYYY-MM-DD."},
           "extend_months": {"type": "integer", "description": "1-120."}}, ["item"]),
    _tool("update_expiry", "Change an expiry date entry: name, date, remind_days, category or notes.",
          {"item": _EXPIRY_REF, "fields": {"type": "object"}}, ["item", "fields"]),
    _tool("delete_expiry", "Delete an expiry date entry.", {"item": _EXPIRY_REF}, ["item"]),
]

_ROUTINE_REF = {"type": "string", "description": "The routine's name (or part of it) or id."}

ROUTINE_SCHEMAS = [
    _tool("add_routine", "Create a routine: a named checklist you repeat (morning routine, evening shutdown). Steps are "
                         "ticked per day and the streak of fully done days is tracked.",
          {"name": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string"}},
           "days": {"type": "string", "description": "daily (default), weekdays, weekends or names such as 'mon, wed, fri'."}},
          ["name", "steps"]),
    _tool("get_routines", "All routines with today's progress and streak; give a routine to see its steps.",
          {"routine": _ROUTINE_REF}, []),
    _tool("check_routine_step", "Tick (or untick with undo) one step of a routine for today, or 'all' steps. A date up "
                                "to 7 days back is allowed.",
          {"routine": _ROUTINE_REF, "step": {"type": "string", "description": "The step's id, some words from it, or 'all'."},
           "undo": {"type": "boolean"}, "date": {"type": "string", "description": "YYYY-MM-DD, default today."}},
          ["routine", "step"]),
    _tool("update_routine", "Change a routine: name, days or steps (the full new list; unchanged steps keep their ticks).",
          {"routine": _ROUTINE_REF, "fields": {"type": "object"}}, ["routine", "fields"]),
    _tool("delete_routine", "Delete a routine and its history.", {"routine": _ROUTINE_REF}, ["routine"]),
]

_GIFT_REF = {"type": "string", "description": "The gift idea's id or some words from it."}

GIFT_SCHEMAS = [
    _tool("add_gift_idea", "Save a gift idea for a person (a name from your people list gets their birthday linked).",
          {"person": {"type": "string"}, "idea": {"type": "string"}, "price": {"type": "number"},
           "occasion": {"type": "string", "description": "e.g. birthday, wedding."},
           "status": {"type": "string", "enum": ["idea", "bought", "given"]}, "notes": {"type": "string"}},
          ["person", "idea"]),
    _tool("get_gift_ideas", "Gift ideas grouped by person, with what was bought or given and the birthdays coming up "
                            "with no gift bought yet.",
          {"person": {"type": "string"}, "status": {"type": "string", "enum": ["idea", "bought", "given"]}}, []),
    _tool("update_gift_idea", "Change a gift idea: person, idea, price, occasion, status (idea, bought, given) or notes.",
          {"gift": _GIFT_REF, "fields": {"type": "object"}}, ["gift", "fields"]),
    _tool("delete_gift_idea", "Delete a gift idea.", {"gift": _GIFT_REF}, ["gift"]),
]

_DECISION_REF = {"type": "string", "description": "The decision's id or some words from its title."}

DECISION_SCHEMAS = [
    _tool("add_decision", "Write down a decision: the options, what you chose and why, what you expect and how "
                          "confident you are. A review date (default in 30 days) is set so you can check how it went.",
          {"title": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
           "choice": {"type": "string"}, "reasoning": {"type": "string"}, "expected": {"type": "string"},
           "confidence": {"type": "integer", "description": "1-10."},
           "review": {"type": "string", "description": "YYYY-MM-DD, in 3 weeks or a weekday. Default in 30 days."}},
          ["title"]),
    _tool("get_decisions", "Decisions: open (default), due for review, reviewed (with how confidence compared with "
                           "outcomes) or all.",
          {"status": {"type": "string", "enum": ["open", "due", "reviewed", "all"]}}, []),
    _tool("review_decision", "Record how a decision turned out, rated 1 (bad) to 5 (great), and what you learned.",
          {"decision": _DECISION_REF, "outcome": {"type": "string"}, "rating": {"type": "integer", "description": "1-5."},
           "lessons": {"type": "string"}}, ["decision", "outcome", "rating"]),
    _tool("update_decision", "Change a decision: title, options, choice, reasoning, expected, confidence, review, "
                             "outcome or lessons.",
          {"decision": _DECISION_REF, "fields": {"type": "object"}}, ["decision", "fields"]),
    _tool("delete_decision", "Delete a decision.", {"decision": _DECISION_REF}, ["decision"]),
]

WEEKAHEAD_SCHEMAS = [
    _tool("get_week_ahead", "One calendar of everything with a date in the coming days: due tasks, time blocks, planned "
                            "meals, birthdays, renewals, debts, countdowns, chores, expiry dates, trips and decisions to "
                            "review. Overdue items first. Use for 'what is coming up this week'.",
          {"days": {"type": "integer", "description": "1-14, default 7."}}, []),
]

SEARCH_SCHEMAS = [
    _tool("search_everything", "Search all your planner data at once (tasks, notes, lists, people, subscriptions, "
                               "savings, debts, countdowns, supplies, symptoms, recipes, meal plan, trips, objectives, "
                               "time blocks, chores, expiry dates, routines, gift ideas, decisions, reminders, habits, goals) for some words. Results are grouped by area "
                               "with ids you can use in the matching tools. For things you logged, use search_logs.",
          {"query": {"type": "string"},
           "areas": {"type": "array", "items": {"type": "string"}, "description": "Only these areas, e.g. notes, tasks."},
           "limit": {"type": "integer", "description": "Per area, 1-20, default 5."}}, ["query"]),
]

CLOSING_SCHEMAS = [
    _tool("get_closing_summary", "A wrap-up of the day (or the week): what got done, what was logged, spending and "
                                 "income, habits and what is left open, then a preview of tomorrow (or next week). "
                                 "Use for 'close my day' or 'weekly review'.",
          {"period": {"type": "string", "enum": ["day", "week"], "description": "Default day."}}, []),
]

REPAIR_SCHEMAS = [
    _tool("get_repair_suggestions", "For every problem the data check finds in the planner data, the exact entry and "
                                    "the tool call that would fix it. Read-only: nothing is changed.",
          {}, []),
]

PLANNER_SCHEMAS = (TASK_SCHEMAS + BODY_SCHEMAS + SUBSCRIPTION_SCHEMAS + PEOPLE_SCHEMAS + AGENDA_SCHEMAS
                   + LIST_SCHEMAS + SAVINGS_SCHEMAS + SYMPTOM_SCHEMAS + NOTE_SCHEMAS
                   + INCOME_SCHEMAS + DEBT_SCHEMAS + COUNTDOWN_SCHEMAS + SUPPLY_SCHEMAS
                   + TIMEBLOCK_SCHEMAS + OKR_SCHEMAS + RECIPE_SCHEMAS + TRIP_SCHEMAS + SEARCH_SCHEMAS
                   + CLOSING_SCHEMAS + REPAIR_SCHEMAS + CHORE_SCHEMAS + EXPIRY_SCHEMAS + ROUTINE_SCHEMAS
                   + GIFT_SCHEMAS + DECISION_SCHEMAS + WEEKAHEAD_SCHEMAS)

TOOL_MODULES: Dict[str, str] = {}
for _schemas, _module in ((TASK_SCHEMAS, "tasks"), (BODY_SCHEMAS, "body"), (SUBSCRIPTION_SCHEMAS, "subscriptions"),
                          (PEOPLE_SCHEMAS, "people"), (AGENDA_SCHEMAS, "agenda"), (LIST_SCHEMAS, "lists"),
                          (SAVINGS_SCHEMAS, "savings"), (SYMPTOM_SCHEMAS, "symptoms"), (NOTE_SCHEMAS, "notes"),
                          (INCOME_SCHEMAS, "income"), (DEBT_SCHEMAS, "debts"), (COUNTDOWN_SCHEMAS, "countdowns"),
                          (SUPPLY_SCHEMAS, "supplies"), (TIMEBLOCK_SCHEMAS, "timeblocks"), (OKR_SCHEMAS, "okrs"),
                          (RECIPE_SCHEMAS, "recipes"), (TRIP_SCHEMAS, "trips"), (SEARCH_SCHEMAS, "finder"),
                          (CLOSING_SCHEMAS, "closing"), (REPAIR_SCHEMAS, "repair_hints"), (CHORE_SCHEMAS, "chores"),
                          (EXPIRY_SCHEMAS, "expiries"), (ROUTINE_SCHEMAS, "routines"), (GIFT_SCHEMAS, "gifts"),
                          (DECISION_SCHEMAS, "decisions"), (WEEKAHEAD_SCHEMAS, "weekahead")):
    for _s in _schemas:
        TOOL_MODULES[_s["function"]["name"]] = _module
