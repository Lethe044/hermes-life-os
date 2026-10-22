"""
Hermes Life OS - tool schemas for the planner modules
=======================================================
Pure data: the schemas of the tools that live in tasks.py, body.py,
subscriptions.py, people.py, agenda.py, lists.py, savings.py,
symptoms.py, notes.py, income.py, debts.py, countdowns.py
and supplies.py, plus the tool name -> module map
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

PLANNER_SCHEMAS = (TASK_SCHEMAS + BODY_SCHEMAS + SUBSCRIPTION_SCHEMAS + PEOPLE_SCHEMAS + AGENDA_SCHEMAS
                   + LIST_SCHEMAS + SAVINGS_SCHEMAS + SYMPTOM_SCHEMAS + NOTE_SCHEMAS
                   + INCOME_SCHEMAS + DEBT_SCHEMAS + COUNTDOWN_SCHEMAS + SUPPLY_SCHEMAS)

TOOL_MODULES: Dict[str, str] = {}
for _schemas, _module in ((TASK_SCHEMAS, "tasks"), (BODY_SCHEMAS, "body"), (SUBSCRIPTION_SCHEMAS, "subscriptions"),
                          (PEOPLE_SCHEMAS, "people"), (AGENDA_SCHEMAS, "agenda"), (LIST_SCHEMAS, "lists"),
                          (SAVINGS_SCHEMAS, "savings"), (SYMPTOM_SCHEMAS, "symptoms"), (NOTE_SCHEMAS, "notes"),
                          (INCOME_SCHEMAS, "income"), (DEBT_SCHEMAS, "debts"), (COUNTDOWN_SCHEMAS, "countdowns"),
                          (SUPPLY_SCHEMAS, "supplies")):
    for _s in _schemas:
        TOOL_MODULES[_s["function"]["name"]] = _module
