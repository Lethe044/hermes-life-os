"""
Hermes Life OS - tool schemas for the planner modules
=======================================================
Pure data: the schemas of the tools that live in tasks.py, body.py,
subscriptions.py, people.py and agenda.py, plus the tool name -> module map
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

PLANNER_SCHEMAS = TASK_SCHEMAS + BODY_SCHEMAS + SUBSCRIPTION_SCHEMAS + PEOPLE_SCHEMAS + AGENDA_SCHEMAS

TOOL_MODULES: Dict[str, str] = {}
for _schemas, _module in ((TASK_SCHEMAS, "tasks"), (BODY_SCHEMAS, "body"), (SUBSCRIPTION_SCHEMAS, "subscriptions"),
                          (PEOPLE_SCHEMAS, "people"), (AGENDA_SCHEMAS, "agenda")):
    for _s in _schemas:
        TOOL_MODULES[_s["function"]["name"]] = _module
