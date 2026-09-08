"""
Hermes Life OS - Meal Summary
=================================
Summarizes recent meals logged via log_meal - totals, breakdown by
meal time (breakfast/lunch/dinner/snack/unknown), average calories per
meal and per logged day, and the most frequently logged foods. Pure
local arithmetic over data already in nutrition.json (via
load_nutrition), no new tracking or storage of its own, no network
call.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict

from storage import load_nutrition


def compute_meal_summary(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "total_meals", "days_logged", "avg_calories_per_meal",
    "avg_calories_per_day", "by_meal_time": {time: count},
    "top_foods": [(food, count), ...]} over the last `days` days.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    meals = [m for m in load_nutrition() if m.get("date", "") >= cutoff]

    if not meals:
        return {"days": days, "total_meals": 0, "days_logged": 0,
                "avg_calories_per_meal": 0.0, "avg_calories_per_day": 0.0,
                "by_meal_time": {}, "top_foods": []}

    total_calories = sum(m.get("calories", 0) for m in meals)
    days_logged = len({m.get("date", "") for m in meals})
    by_meal_time = Counter(m.get("time", "unknown") for m in meals)
    top_foods = Counter(m.get("food", "").strip().lower() for m in meals if m.get("food")).most_common(5)

    return {
        "days": days,
        "total_meals": len(meals),
        "days_logged": days_logged,
        "avg_calories_per_meal": round(total_calories / len(meals), 1),
        "avg_calories_per_day": round(total_calories / days_logged, 1) if days_logged else 0.0,
        "by_meal_time": dict(by_meal_time),
        "top_foods": top_foods,
    }


def format_meal_summary(result: Dict[str, Any]) -> str:
    """Turns compute_meal_summary()'s output into a friendly multi-line
    summary."""
    if result["total_meals"] == 0:
        return f"No meals logged in the last {result['days']} days."

    lines = [
        f"{result['total_meals']} meal(s) logged over {result['days_logged']} day(s) "
        f"in the last {result['days']} days.",
        f"Average {result['avg_calories_per_meal']} calories/meal, "
        f"{result['avg_calories_per_day']} calories/logged day.",
    ]
    by_time_str = ", ".join(f"{t}: {c}" for t, c in
                             sorted(result["by_meal_time"].items(), key=lambda kv: -kv[1]))
    lines.append(f"By meal time: {by_time_str}.")
    if result["top_foods"]:
        foods_str = ", ".join(f"{f} ({c})" for f, c in result["top_foods"])
        lines.append(f"Most logged foods: {foods_str}.")
    return "\n".join(lines)
