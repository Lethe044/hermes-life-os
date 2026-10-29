"""
Hermes Life OS - Recipes and Meal Plan
========================================
A recipe book, a meal plan and the shopping list that connects them. A recipe
has ingredients (quantity, unit, name), steps, tags, the number of servings it
makes and optionally the calories per serving and the minutes it takes. It can
be shown scaled to any number of servings. The meal plan puts recipes (or
plain text such as "leftovers") into the breakfast, lunch, dinner and snack
slots of the coming days (the servings decide how much to buy); `shopping_from_plan` adds up everything the planned
recipes need and puts it on a list (the shopping list by default), and
`log_planned_meal` logs a planned meal as eaten in the nutrition log, which
also counts the recipe as cooked so `suggest_recipes` can offer the ones you
have not made in a while.

Stored in recipes.json as {"id", "name", "servings", "ingredients": [{"name",
"quantity", "unit"}], "steps", "tags", "calories", "minutes", "notes",
"created", "times_cooked", "last_cooked"} dicts and in mealplan.json as {"id",
"date", "slot", "recipe_id", "name", "servings", "calories", "eaten"} dicts
(`calories` is per serving). Calories are what you enter, not a measurement or
advice. No network call is made by this module.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import clock

SLOTS = ("breakfast", "lunch", "dinner", "snack")
MAX_RECIPES = 500
MAX_NAME = 80
MAX_INGREDIENTS = 40
MAX_INGREDIENT = 60
MAX_STEPS = 30
MAX_STEP = 300
MAX_TAGS = 8
MAX_TAG = 20
MAX_NOTES = 300
MAX_SERVINGS = 100
MAX_QUANTITY = 100000
MAX_MINUTES = 24 * 60
MAX_CALORIES = 5000
MAX_MEALS = 5000
MAX_MEALS_PER_DAY = 20
MAX_PLAN_DAYS = 31
MAX_REPEAT_DAYS = 14
MAX_SUGGESTIONS = 10
DATE_RANGE_DAYS = 365
DEFAULT_SERVINGS = 2
MAX_SHOPPING_ITEMS = 200
_UNITS = {
    "g": "g", "gram": "g", "grams": "g", "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp", "tbsp": "tbsp", "tablespoon": "tbsp",
    "tablespoons": "tbsp", "cup": "cup", "cups": "cup", "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb", "pinch": "pinch", "pinches": "pinch",
    "can": "can", "cans": "can", "clove": "clove", "cloves": "clove", "slice": "slice", "slices": "slice",
    "bunch": "bunch", "bunches": "bunch", "pack": "pack", "packs": "pack",
}
_QTY_RE = re.compile(r"^(\d+\s*/\s*\d+|\d+(?:[.,]\d+)?)")


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


# ------------------------------------------------------------------ parsing

def _clean_name(value: Any, what: str = "recipe") -> str:
    if not isinstance(value, str) or not " ".join(value.split()):
        raise ValueError(f"the {what} needs a name.")
    name = " ".join(value.split())
    if len(name) > MAX_NAME:
        raise ValueError(f"the name can be at most {MAX_NAME} characters.")
    return name


def _whole(value: Any, low: int, high: int, what: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a whole number from {low} to {high}.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a whole number from {low} to {high}.") from None
    if number != number or number != int(number) or not low <= number <= high:
        raise ValueError(f"{what} must be a whole number from {low} to {high}.")
    return int(number)


def _quantity(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("an ingredient quantity must be a positive number.")
    try:
        if isinstance(value, str) and "/" in value:
            top, bottom = value.split("/", 1)
            number = float(top) / float(bottom)
        else:
            number = float(str(value).replace(",", ".")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        raise ValueError("an ingredient quantity must be a positive number.") from None
    if math.isnan(number) or math.isinf(number) or not 0 < number <= MAX_QUANTITY:
        raise ValueError(f"an ingredient quantity must be above 0 and at most {MAX_QUANTITY}.")
    return round(number, 3)


def _unit(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or len(value.strip()) > 12:
        raise ValueError("an ingredient unit must be short text such as g, ml, tbsp or cup.")
    key = value.strip().lower()
    return _UNITS.get(key, key)


def parse_ingredient(value: Any) -> Dict[str, Any]:
    """{"name", "quantity", "unit"} from "200 g flour", "2 eggs", "salt" or a
    {"name", "quantity", "unit"} dict. Raises ValueError."""
    if isinstance(value, dict):
        name, qty, unit = value.get("name"), _quantity(value.get("quantity")), _unit(value.get("unit"))
    elif isinstance(value, str):
        text = " ".join(value.split())
        m = _QTY_RE.match(text)
        qty, unit, name = None, None, text
        if m:
            qty = _quantity(m.group(1).replace(" ", ""))
            rest = text[m.end():].strip()
            first, _, after = rest.partition(" ")
            if first.lower() in _UNITS and after.strip():
                unit, name = _UNITS[first.lower()], after.strip()
            else:
                name = rest
    else:
        raise ValueError("an ingredient must be text like '200 g flour' or {name, quantity, unit}.")
    if not isinstance(name, str) or not " ".join(name.split()):
        raise ValueError("an ingredient needs a name.")
    name = " ".join(name.split())
    if len(name) > MAX_INGREDIENT:
        raise ValueError(f"an ingredient name can be at most {MAX_INGREDIENT} characters.")
    return {"name": name, "quantity": qty, "unit": unit}


def parse_ingredients(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        value = [p for p in re.split(r"\n|;|,\s", value) if p.strip()]
    if not isinstance(value, list) or not value:
        raise ValueError("a recipe needs ingredients: a list like ['200 g flour', '2 eggs'].")
    if len(value) > MAX_INGREDIENTS:
        raise ValueError(f"a recipe can have at most {MAX_INGREDIENTS} ingredients.")
    return [parse_ingredient(v) for v in value]


def parse_steps(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [p for p in value.split("\n") if p.strip()]
    if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
        raise ValueError("steps must be a list of texts.")
    steps = [" ".join(s.split()) for s in value if s.strip()]
    if len(steps) > MAX_STEPS:
        raise ValueError(f"a recipe can have at most {MAX_STEPS} steps.")
    if any(len(s) > MAX_STEP for s in steps):
        raise ValueError(f"a step can be at most {MAX_STEP} characters.")
    return steps


def parse_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.replace(";", ",").split(",")
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise ValueError("tags must be a list of short words.")
    out: List[str] = []
    for t in value:
        t = " ".join(t.strip().lower().split())
        if not t:
            continue
        if len(t) > MAX_TAG:
            raise ValueError(f"a tag can be at most {MAX_TAG} characters.")
        if t not in out:
            out.append(t)
    if len(out) > MAX_TAGS:
        raise ValueError(f"a recipe can have at most {MAX_TAGS} tags.")
    return out


def _optional_whole(value: Any, high: int, what: str) -> Optional[int]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _whole(value, 1, high, what)


def _notes(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("notes must be text.")
    return value.strip()[:MAX_NOTES]


def parse_slot(value: Any) -> str:
    if not isinstance(value, str) or value.strip().lower() not in SLOTS:
        raise ValueError(f"the slot must be one of {', '.join(SLOTS)}.")
    return value.strip().lower()


def parse_date(value: Any) -> str:
    import tasks
    day = tasks.parse_due(value) or clock.today_str()
    if abs((clock.parse_day(day) - clock.today()).days) > DATE_RANGE_DAYS:
        raise ValueError(f"the date must be within {DATE_RANGE_DAYS} days of today.")
    return day


_COUNTED_UNITS = ("clove", "slice", "can", "pack", "bunch", "cup")


def _qty_text(qty: Optional[float], unit: Optional[str]) -> str:
    if qty is None:
        return ""
    if unit and unit in _COUNTED_UNITS and qty != 1:
        unit = "bunches" if unit == "bunch" else unit + "s"
    return f"{qty:g}" + (f" {unit}" if unit else "")


# ------------------------------------------------------------------ storage

def _fill_ids(rows: List[Any], save) -> List[Any]:
    seen = {r.get("id") for r in rows if isinstance(r, dict) and r.get("id")}
    changed = False
    for r in rows:
        if isinstance(r, dict) and not r.get("id"):
            new = new_id()
            while new in seen:
                new = new_id()
            seen.add(new)
            r["id"] = new
            changed = True
    if changed:
        save(rows)
    return rows


def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_recipes()
    return _fill_ids(rows, _storage().save_recipes) if isinstance(rows, list) else []


def _load_plan() -> List[Dict[str, Any]]:
    rows = _storage().load_mealplan()
    return _fill_ids(rows, _storage().save_mealplan) if isinstance(rows, list) else []


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def ingredients_of(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    ings = recipe.get("ingredients")
    return [i for i in ings if isinstance(i, dict) and isinstance(i.get("name"), str) and i["name"].strip()] \
        if isinstance(ings, list) else []


def _servings(recipe: Dict[str, Any]) -> int:
    s = recipe.get("servings")
    return int(s) if isinstance(s, (int, float)) and not isinstance(s, bool) and s >= 1 else DEFAULT_SERVINGS


def _resolve(rows: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which recipe (its id or some words from its name).")
    key = ref.strip().lower()
    pool = _rows(rows)
    for r in pool:
        if str(r.get("id", "")).lower() == key or str(r.get("name", "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no recipe matches '{ref.strip()}'. Use get_recipes to see them.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} recipes ({'; '.join(str(r.get('name')) for r in hits[:5])}). "
                     f"Use the full name or the id.")


# ------------------------------------------------------------------ recipes

def add_recipe(name: Any, ingredients: Any, steps: Any = None, servings: Any = None, tags: Any = None,
               calories: Any = None, minutes: Any = None, notes: Any = None) -> Dict[str, Any]:
    clean = _clean_name(name)
    ings = parse_ingredients(ingredients)
    rows = _load()
    if len(rows) >= MAX_RECIPES:
        raise ValueError(f"you already have {MAX_RECIPES} recipes.")
    if any(str(r.get("name", "")).lower() == clean.lower() for r in _rows(rows)):
        raise ValueError(f"there is already a recipe called '{clean}'.")
    recipe = {"id": new_id(), "name": clean,
              "servings": DEFAULT_SERVINGS if servings in (None, "") else _whole(servings, 1, MAX_SERVINGS, "servings"),
              "ingredients": ings, "steps": parse_steps(steps), "tags": parse_tags(tags),
              "calories": _optional_whole(calories, MAX_CALORIES, "calories"),
              "minutes": _optional_whole(minutes, MAX_MINUTES, "minutes"), "notes": _notes(notes),
              "created": clock.today_str(), "times_cooked": 0, "last_cooked": None}
    rows.append(recipe)
    _storage().save_recipes(rows)
    return recipe


def update_recipe(ref: Any, fields: Any) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields (name, servings, ingredients, steps, tags, "
                         "calories, minutes, notes).")
    allowed = ("name", "servings", "ingredients", "steps", "tags", "calories", "minutes", "notes")
    unknown = [k for k in fields if k not in allowed]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change {', '.join(allowed)}.")
    rows = _load()
    recipe = _resolve(rows, ref)
    changes: Dict[str, Any] = {}
    if "name" in fields:
        n = _clean_name(fields["name"])
        if any(r is not recipe and str(r.get("name", "")).lower() == n.lower() for r in _rows(rows)):
            raise ValueError(f"there is already a recipe called '{n}'.")
        changes["name"] = n
    if "servings" in fields:
        changes["servings"] = _whole(fields["servings"], 1, MAX_SERVINGS, "servings")
    if "ingredients" in fields:
        changes["ingredients"] = parse_ingredients(fields["ingredients"])
    if "steps" in fields:
        changes["steps"] = parse_steps(fields["steps"])
    if "tags" in fields:
        changes["tags"] = parse_tags(fields["tags"])
    if "calories" in fields:
        changes["calories"] = _optional_whole(fields["calories"], MAX_CALORIES, "calories")
    if "minutes" in fields:
        changes["minutes"] = _optional_whole(fields["minutes"], MAX_MINUTES, "minutes")
    if "notes" in fields:
        changes["notes"] = _notes(fields["notes"])
    recipe.update(changes)
    _storage().save_recipes(rows)
    if "name" in changes:  # planned meals keep a copy of the name; keep it in step
        plan = _load_plan()
        touched = False
        for m in _rows(plan):
            if m.get("recipe_id") == recipe.get("id"):
                m["name"] = changes["name"]
                touched = True
        if touched:
            _storage().save_mealplan(plan)
    return recipe


def delete_recipe(ref: Any) -> Dict[str, Any]:
    """Deletes a recipe. Planned meals that used it stay in the plan as plain
    text (they just no longer add to the shopping list); returns the recipe
    and how many planned meals were affected."""
    rows = _load()
    recipe = _resolve(rows, ref)
    _storage().save_recipes([r for r in rows if r is not recipe])
    plan = _load_plan()
    affected = [m for m in _rows(plan) if m.get("recipe_id") == recipe.get("id")]
    for m in affected:
        m["recipe_id"] = None
    if affected:
        _storage().save_mealplan(plan)
    return {"recipe": recipe, "unlinked": len(affected)}


def list_recipes(tag: Any = None, query: Any = None, limit: Any = 30) -> List[Dict[str, Any]]:
    n = _whole(limit, 1, 200, "limit")
    rows = _rows(_load())
    if tag not in (None, ""):
        wanted = parse_tags([tag])
        rows = [r for r in rows if wanted and wanted[0] in (r.get("tags") or [])]
    if query not in (None, ""):
        if not isinstance(query, str):
            raise ValueError("the search words must be text.")
        q = query.strip().lower()
        rows = [r for r in rows if q in str(r.get("name", "")).lower()
                or any(q in str(i.get("name", "")).lower() for i in ingredients_of(r))]
    return sorted(rows, key=lambda r: str(r.get("name", "")).lower())[:n]


def suggest(tag: Any = None, max_minutes: Any = None, limit: Any = 5) -> List[Dict[str, Any]]:
    """Recipes never cooked first, then the ones cooked longest ago."""
    n = _whole(limit, 1, MAX_SUGGESTIONS, "limit")
    rows = list_recipes(tag, None, 200)
    if max_minutes not in (None, ""):
        cap = _whole(max_minutes, 1, MAX_MINUTES, "max_minutes")
        rows = [r for r in rows if isinstance(r.get("minutes"), (int, float)) and r["minutes"] <= cap]
    return sorted(rows, key=lambda r: (str(r.get("last_cooked") or ""), str(r.get("name", "")).lower()))[:n]


def scaled_ingredients(recipe: Dict[str, Any], servings: Optional[int] = None) -> List[Dict[str, Any]]:
    factor = (servings / _servings(recipe)) if servings else 1.0
    out = []
    for i in ingredients_of(recipe):
        q = i.get("quantity")
        ok = isinstance(q, (int, float)) and not isinstance(q, bool) and q > 0
        out.append({"name": i["name"].strip(), "unit": i.get("unit") if isinstance(i.get("unit"), str) else None,
                    "quantity": round(q * factor, 3) if ok else None})
    return out


# ------------------------------------------------------------------ meal plan

def plan_meal(date: Any, slot: Any, recipe: Any = None, text: Any = None, servings: Any = None,
              repeat_days: Any = 1) -> List[Dict[str, Any]]:
    """Plans a meal for a slot, optionally repeated on the following days.
    Either `recipe` or `text`. Raises ValueError, adding nothing."""
    if (recipe in (None, "")) == (text in (None, "")):
        raise ValueError("give either a recipe or some text (like 'leftovers'), not both and not neither.")
    day = parse_date(date)
    sl = parse_slot(slot)
    count = _whole(repeat_days, 1, MAX_REPEAT_DAYS, "repeat_days")
    rec = _resolve(_load(), recipe) if recipe not in (None, "") else None
    if rec is None:
        name = _clean_name(text, "meal")
    else:
        name = str(rec.get("name"))
    n_serv = _whole(servings, 1, MAX_SERVINGS, "servings") if servings not in (None, "") else (
        _servings(rec) if rec else 1)
    calories = rec.get("calories") if rec and isinstance(rec.get("calories"), (int, float)) else None
    plan = _load_plan()
    if len(plan) + count > MAX_MEALS:
        raise ValueError(f"the meal plan is full ({MAX_MEALS} meals) - clear old days first.")
    first = clock.parse_day(day)
    new_rows = []
    for i in range(count):
        d = (first + timedelta(days=i)).isoformat()
        if abs((clock.parse_day(d) - clock.today()).days) > DATE_RANGE_DAYS:
            raise ValueError(f"the date must be within {DATE_RANGE_DAYS} days of today.")
        if sum(1 for m in _rows(plan) if m.get("date") == d) >= MAX_MEALS_PER_DAY:
            raise ValueError(f"{d} already has {MAX_MEALS_PER_DAY} planned meals.")
        new_rows.append({"id": new_id(), "date": d, "slot": sl, "recipe_id": rec.get("id") if rec else None,
                         "name": name, "servings": n_serv, "calories": calories, "eaten": False})
    plan.extend(new_rows)
    _storage().save_mealplan(plan)
    return new_rows


def _plan_range(date: Any, days: Any) -> Tuple[str, str, int]:
    n = _whole(days, 1, MAX_PLAN_DAYS, "days")
    first = parse_date(date)
    return first, (clock.parse_day(first) + timedelta(days=n - 1)).isoformat(), n


def meals_between(first: str, last: str) -> List[Dict[str, Any]]:
    out = [m for m in _rows(_load_plan()) if isinstance(m.get("date"), str) and first <= m["date"] <= last
           and m.get("slot") in SLOTS]
    return sorted(out, key=lambda m: (m["date"], SLOTS.index(m["slot"]), str(m.get("name", "")).lower()))


def clear_meals(meal: Any = None, date: Any = None, slot: Any = None) -> List[Dict[str, Any]]:
    """Removes one planned meal (by id) or every planned meal of a day (and
    slot). Raises ValueError when nothing matches."""
    plan = _load_plan()
    if meal not in (None, ""):
        if not isinstance(meal, str):
            raise ValueError("the meal id must be text.")
        hit = [m for m in _rows(plan) if str(m.get("id", "")).lower() == meal.strip().lower()]
        if not hit:
            raise ValueError(f"no planned meal has the id '{meal.strip()}'. Use get_meal_plan to see ids.")
    else:
        if date in (None, ""):
            raise ValueError("give a meal id, or a date (and optionally a slot) to clear.")
        day = parse_date(date)
        sl = parse_slot(slot) if slot not in (None, "") else None
        hit = [m for m in _rows(plan) if m.get("date") == day and (sl is None or m.get("slot") == sl)]
        if not hit:
            raise ValueError(f"nothing is planned for {day}{' ' + sl if sl else ''}.")
    gone = {id(m) for m in hit}
    _storage().save_mealplan([m for m in plan if id(m) not in gone])
    return hit


def _portions(value: Any) -> float:
    if value in (None, ""):
        return 1.0
    if isinstance(value, bool):
        raise ValueError("portions must be a number from 0.25 to 20.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("portions must be a number from 0.25 to 20.") from None
    if math.isnan(number) or not 0.25 <= number <= 20:
        raise ValueError("portions must be a number from 0.25 to 20.")
    return round(number, 2)


def log_planned_meal(meal: Any, date: Any, dispatch: Any, portions: Any = None) -> Dict[str, Any]:
    """Logs a planned meal as eaten in the nutrition log (through log_meal) and
    marks it eaten; its recipe counts as cooked. `meal` is an id or words from
    its name, looked up among the meals of `date` (today by default).
    `portions` is how much YOU ate in servings (default 1): the planned
    servings only decide how much to buy."""
    eaten = _portions(portions)
    if not isinstance(meal, str) or not meal.strip():
        raise ValueError("say which planned meal (its id or some words from its name).")
    if dispatch is None:
        raise ValueError("logging is not available here.")
    plan = _load_plan()
    key = meal.strip().lower()
    pool = _rows(plan)
    row = next((m for m in pool if str(m.get("id", "")).lower() == key), None)
    if row is None:
        day = parse_date(date)
        today_rows = [m for m in pool if m.get("date") == day]
        hits = [m for m in today_rows if key in str(m.get("name", "")).lower() or key == m.get("slot")]
        pending = [m for m in hits if not m.get("eaten")]
        hits = pending or hits
        if not hits:
            raise ValueError(f"no planned meal matches '{meal.strip()}' on {day}. Use get_meal_plan to see ids.")
        if len(hits) > 1:
            raise ValueError(f"'{meal.strip()}' matches {len(hits)} meals on {day} ("
                             + "; ".join(f"[id={m['id']}] {m.get('slot')}: {m.get('name')}" for m in hits[:5])
                             + "). Use the id.")
        row = hits[0]
    if row.get("eaten"):
        raise ValueError(f"'{row.get('name')}' on {row.get('date')} is already logged as eaten.")
    if row.get("slot") not in SLOTS or not isinstance(row.get("date"), str):
        raise ValueError("this planned meal has no readable date or slot.")
    args: Dict[str, Any] = {"meal_time": row["slot"], "food": str(row.get("name", "")), "date": row["date"]}
    per = row.get("calories")
    if isinstance(per, (int, float)) and not isinstance(per, bool) and per > 0:
        args["calories"] = int(round(per * eaten))
    result = dispatch("log_meal", args)
    if not str(result).startswith("Meal logged"):
        raise ValueError(str(result).replace("Not logged: ", "", 1))
    row["eaten"] = True
    _storage().save_mealplan(plan)
    recipes = _load()
    rec = next((r for r in _rows(recipes) if row.get("recipe_id") and r.get("id") == row.get("recipe_id")), None)
    if rec is not None:
        rec["times_cooked"] = (rec.get("times_cooked") if isinstance(rec.get("times_cooked"), int) else 0) + 1
        if str(rec.get("last_cooked") or "") < row["date"]:
            rec["last_cooked"] = row["date"]
        _storage().save_recipes(recipes)
    return {"meal": row, "log": str(result)}


def shopping_needs(first: str, last: str, include_eaten: bool = False,
                   skip: Optional[List[str]] = None) -> Dict[str, Any]:
    """What the planned recipes between two dates need: [{"name", "quantity"
    (text)}], how many meals were used, the meals without a usable recipe."""
    recipes = {r.get("id"): r for r in _rows(_load())}
    skip_set = {s.strip().lower() for s in (skip or []) if isinstance(s, str)}
    groups: Dict[str, Dict[str, Any]] = {}
    used, plain = 0, []
    for m in meals_between(first, last):
        if m.get("eaten") and not include_eaten:
            continue
        rec = recipes.get(m.get("recipe_id")) if m.get("recipe_id") else None
        if rec is None:
            plain.append(str(m.get("name", "?")))
            continue
        used += 1
        servings = m.get("servings") if isinstance(m.get("servings"), (int, float)) and m.get("servings") >= 1 else None
        for ing in scaled_ingredients(rec, int(servings) if servings else None):
            if ing["name"].lower() in skip_set:
                continue
            g = groups.setdefault(ing["name"].lower(), {"name": ing["name"], "parts": {}})
            g["parts"][ing["unit"]] = g["parts"].get(ing["unit"], 0) + (ing["quantity"] or 0)
    items = []
    for g in sorted(groups.values(), key=lambda g: g["name"].lower()):
        bits = [_qty_text(round(q, 3), u) for u, q in g["parts"].items() if q]
        qty = " + ".join(bits)
        items.append({"name": g["name"], "quantity": qty if len(qty) <= 30 else qty[:27] + "..."})
    return {"items": items, "meals": used, "plain": plain}


def shopping_from_plan(date: Any = None, days: Any = 7, list_name: Any = None, include_eaten: bool = False,
                       skip: Any = None) -> Dict[str, Any]:
    import lists
    first, last, n = _plan_range(date, days)
    if skip is not None and (not isinstance(skip, list) or not all(isinstance(s, str) for s in skip)):
        raise ValueError("skip must be a list of ingredient names (for example ['salt', 'water']).")
    if not isinstance(include_eaten, bool):
        raise ValueError("include_eaten must be true or false.")
    target = lists.norm_list(list_name)
    needs = shopping_needs(first, last, include_eaten, skip)
    items = needs["items"]
    if not items:
        raise ValueError(f"nothing to buy: no planned recipe between {first} and {last} needs ingredients "
                         f"(meals without a recipe, eaten meals and skipped items are left out).")
    if len(items) > MAX_SHOPPING_ITEMS:
        raise ValueError(f"that is {len(items)} different ingredients - plan fewer days at a time.")
    if any(len(i["name"]) > lists.MAX_TEXT for i in items):
        raise ValueError(f"an ingredient name is longer than {lists.MAX_TEXT} characters.")
    if len(lists._load()) + len(items) > lists.MAX_ITEMS_TOTAL:
        raise ValueError(f"lists are full ({lists.MAX_ITEMS_TOTAL} items) - clear some first.")
    added, skipped = [], []
    for i in items:
        res = lists.add_items(target, [i["name"]], i["quantity"] or None)
        (added if res["added"] else skipped).append(i)
    return {"list": target, "from": first, "to": last, "meals": needs["meals"], "added": added,
            "skipped": skipped, "plain": needs["plain"]}


# ------------------------------------------------------------------ formatting

def format_recipe_line(r: Dict[str, Any]) -> str:
    bits = [f"serves {_servings(r)}"]
    if isinstance(r.get("minutes"), (int, float)):
        bits.append(f"{int(r['minutes'])} min")
    if isinstance(r.get("calories"), (int, float)):
        bits.append(f"{int(r['calories'])} cal each")
    if r.get("tags"):
        bits.append("tags: " + ", ".join(str(t) for t in r["tags"]))
    cooked = r.get("times_cooked") if isinstance(r.get("times_cooked"), int) else 0
    if cooked:
        bits.append(f"cooked {cooked}x, last {r.get('last_cooked')}")
    return f"{r.get('name', '?')} ({'; '.join(bits)}) [id={r.get('id', '?')}]"


def format_recipes(rows: List[Dict[str, Any]], empty: str = "No recipes yet. Add one with add_recipe.",
                   suffix: str = "") -> str:
    if not rows:
        return empty
    return (f"{len(rows)} recipe{'s' if len(rows) != 1 else ''}{suffix}:\n"
            + "\n".join(f"- {format_recipe_line(r)}" for r in rows))


def format_recipe(r: Dict[str, Any], servings: Optional[int] = None) -> str:
    base = _servings(r)
    head = format_recipe_line(r)
    if servings and servings != base:
        head += f"\nScaled from {base} to {servings} servings."
    lines = [head, "Ingredients:"]
    for i in scaled_ingredients(r, servings):
        qty = _qty_text(i["quantity"], i["unit"])
        lines.append(f"- {qty + ' ' if qty else ''}{i['name']}")
    steps = [s for s in (r.get("steps") or []) if isinstance(s, str)] if isinstance(r.get("steps"), list) else []
    if steps:
        lines.append("Steps:")
        lines += [f"{n}. {s}" for n, s in enumerate(steps, 1)]
    if r.get("notes"):
        lines.append(f"Notes: {r['notes']}")
    return "\n".join(lines)


def format_meal(m: Dict[str, Any]) -> str:
    bits = [f"{m.get('servings', 1)} serving{'s' if m.get('servings') != 1 else ''}"]
    if isinstance(m.get("calories"), (int, float)) and not isinstance(m.get("calories"), bool) and m["calories"] > 0:
        bits.append(f"{int(round(m['calories']))} cal per serving")
    state = ", eaten" if m.get("eaten") else ""
    return f"{m.get('slot', '?')}: {m.get('name', '?')} ({', '.join(bits)}{state}) [id={m.get('id', '?')}]"


def format_plan(first: str, last: str, meals: List[Dict[str, Any]]) -> str:
    if not meals:
        return f"No meals planned from {first} to {last}. Add one with plan_meal."
    lines = [f"Meal plan {first} to {last}: {len(meals)} meal{'s' if len(meals) != 1 else ''}."]
    day = clock.parse_day(first)
    end = clock.parse_day(last)
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for m in meals:
        by_day.setdefault(m["date"], []).append(m)
    while day <= end:
        d = day.isoformat()
        lines.append(f"{day.strftime('%a')} {d}")
        if d in by_day:
            lines += [f"  {format_meal(m)}" for m in by_day[d]]
        else:
            lines.append("  nothing planned")
        day += timedelta(days=1)
    return "\n".join(lines)


def format_shopping(res: Dict[str, Any]) -> str:
    def item(i: Dict[str, Any]) -> str:
        return f"{i['name']} ({i['quantity']})" if i["quantity"] else i["name"]
    lines = [f"Added {len(res['added'])} item(s) to the {res['list']} list for {res['meals']} planned "
             f"meal(s) from {res['from']} to {res['to']}."]
    if res["added"]:
        lines.append("Added: " + ", ".join(item(i) for i in res["added"]))
    if res["skipped"]:
        lines.append("Already on the list (left as they are): " + ", ".join(i["name"] for i in res["skipped"]))
    if res["plain"]:
        lines.append(f"Not included (no recipe): {', '.join(res['plain'][:5])}"
                     + (f" and {len(res['plain']) - 5} more" if len(res["plain"]) > 5 else ""))
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], dispatch: Any = None, **_ctx: Any) -> str:
    try:
        if name == "add_recipe":
            r = add_recipe(inp.get("name"), inp.get("ingredients"), inp.get("steps"), inp.get("servings"),
                           inp.get("tags"), inp.get("calories_per_serving"), inp.get("minutes"), inp.get("notes"))
            return "Recipe added: " + format_recipe_line(r)
        if name == "get_recipes":
            rows = list_recipes(inp.get("tag"), inp.get("query"), inp.get("limit", 30))
            return format_recipes(rows, "No recipes match." if (inp.get("tag") or inp.get("query"))
                                  else "No recipes yet. Add one with add_recipe.")
        if name == "get_recipe":
            rec = _resolve(_load(), inp.get("recipe"))
            servings = _whole(inp["servings"], 1, MAX_SERVINGS, "servings") if inp.get("servings") not in (None, "") else None
            return format_recipe(rec, servings)
        if name == "update_recipe":
            return "Recipe updated: " + format_recipe_line(update_recipe(inp.get("recipe"), inp.get("fields")))
        if name == "delete_recipe":
            res = delete_recipe(inp.get("recipe"))
            extra = f" {res['unlinked']} planned meal(s) stay in the plan as plain text." if res["unlinked"] else ""
            return f"Deleted recipe {res['recipe'].get('name')}. This can't be undone.{extra}"
        if name == "suggest_recipes":
            rows = suggest(inp.get("tag"), inp.get("max_minutes"), inp.get("limit", 5))
            return format_recipes(rows, "No recipe fits. Add some with add_recipe or relax the filters.",
                                  " to cook next")
        if name == "plan_meal":
            rows = plan_meal(inp.get("date"), inp.get("slot"), inp.get("recipe"), inp.get("text"),
                             inp.get("servings"), inp.get("repeat_days", 1))
            if len(rows) == 1:
                return f"Planned for {rows[0]['date']}: " + format_meal(rows[0])
            return (f"Planned on {len(rows)} days ({rows[0]['date']} to {rows[-1]['date']}): "
                    f"{rows[0]['slot']}: {rows[0]['name']} ({rows[0]['servings']} servings each day)")
        if name == "get_meal_plan":
            first, last, _n = _plan_range(inp.get("date"), inp.get("days", 7))
            return format_plan(first, last, meals_between(first, last))
        if name == "clear_meals":
            gone = clear_meals(inp.get("meal"), inp.get("date"), inp.get("slot"))
            return f"Cleared {len(gone)} planned meal{'s' if len(gone) != 1 else ''}: " + "; ".join(
                f"{m.get('date')} {m.get('slot')} {m.get('name')}" for m in gone[:5]) + (" ..." if len(gone) > 5 else "")
        if name == "log_planned_meal":
            res = log_planned_meal(inp.get("meal"), inp.get("date"), dispatch, inp.get("portions"))
            return f"Logged planned meal as eaten: {format_meal(res['meal'])}\n{res['log']}"
        if name == "shopping_from_plan":
            return format_shopping(shopping_from_plan(inp.get("date"), inp.get("days", 7), inp.get("list"),
                                                      inp.get("include_eaten", False), inp.get("skip")))
    except (ValueError, TypeError) as e:
        verb = {"add_recipe": "Recipe not added", "get_recipes": "Cannot list recipes",
                "get_recipe": "Cannot show the recipe", "suggest_recipes": "Cannot suggest recipes",
                "plan_meal": "Meal not planned", "get_meal_plan": "Cannot show the meal plan",
                "clear_meals": "Nothing cleared", "log_planned_meal": "Not logged",
                "shopping_from_plan": "Nothing added to the list"}.get(name, "Recipe not changed")
        return f"{verb}: {e}"
    return f"Unknown recipe tool: {name}"
