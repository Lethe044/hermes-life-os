"""Recipes, the meal plan and the shopping list that connects them."""

from __future__ import annotations

import pytest

SOUP = {"name": "Lentil soup", "servings": 4, "ingredients": ["200 g red lentils", "2 cloves garlic", "1 onion", "salt"],
        "steps": ["Chop", "Simmer 25 min"], "tags": ["Soup", "vegan"], "calories_per_serving": 320, "minutes": 35}
OMELETTE = {"name": "Omelette", "servings": 1, "ingredients": ["2 eggs", "1 tbsp olive oil", "salt"], "minutes": 10,
            "calories_per_serving": 250}


def recipe(p, **kw):
    args = {**SOUP, **kw}
    out = p.dispatch_tool("add_recipe", args)
    assert out.startswith("Recipe added: "), out
    return out.split("[id=")[1].split("]")[0]


def recipes():
    import storage
    return storage.load_recipes()


def plan():
    import storage
    return storage.load_mealplan()


class TestIngredientParsing:
    @pytest.mark.parametrize("text,expected", [
        ("200 g flour", (200, "g", "flour")), ("200g flour", (200, "g", "flour")), ("2 eggs", (2, None, "eggs")),
        ("salt", (None, None, "salt")), ("1/2 tsp salt", (0.5, "tsp", "salt")), ("1,5 kg potatoes", (1.5, "kg", "potatoes")),
        ("1.5 Litres milk", (1.5, "l", "milk")), ("3 cups", (3, None, "cups")), ("2 cloves garlic", (2, "clove", "garlic")),
        ("  1   can   tomatoes ", (1, "can", "tomatoes")), ("1 Tablespoon olive oil", (1, "tbsp", "olive oil")),
        ("2 large onions", (2, None, "large onions"))])
    def test_strings(self, planner, text, expected):
        import recipes as r
        i = r.parse_ingredient(text)
        assert (i["quantity"], i["unit"], i["name"]) == expected

    def test_dicts(self, planner):
        import recipes as r
        assert r.parse_ingredient({"name": "Rice", "quantity": "250", "unit": "Grams"}) == {"name": "Rice", "quantity": 250.0, "unit": "g"}
        assert r.parse_ingredient({"name": "Salt"}) == {"name": "Salt", "quantity": None, "unit": None}

    @pytest.mark.parametrize("bad", ["", "   ", "200 g", 5, None, {"quantity": 2}, {"name": "x", "quantity": 0}, {"name": "x", "quantity": -1},
                                     {"name": "x", "quantity": "lots"}, {"name": "x", "quantity": True}, {"name": "x", "quantity": 1e9},
                                     {"name": "x", "unit": "u" * 13}, {"name": "x" * 61}, "0 g flour", {"name": "x", "quantity": "1/0"}])
    def test_bad(self, planner, bad):
        import recipes as r
        if bad == "200 g":
            assert r.parse_ingredient(bad)["name"] == "g"   # a unit with nothing after it is just a name
            return
        with pytest.raises(ValueError):
            r.parse_ingredient(bad)

    def test_a_text_of_ingredients(self, planner):
        import recipes as r
        got = r.parse_ingredients("2 eggs, 200 g flour\n1,5 kg salt; pepper")
        assert [(i["name"], i["quantity"]) for i in got] == [("eggs", 2), ("flour", 200), ("salt", 1.5), ("pepper", None)]


class TestAddAndShow:
    def test_stored_shape(self, planner):
        rid = recipe(planner)
        assert recipes() == [{"id": rid, "name": "Lentil soup", "servings": 4, "steps": ["Chop", "Simmer 25 min"],
                              "ingredients": [{"name": "red lentils", "quantity": 200.0, "unit": "g"},
                                              {"name": "garlic", "quantity": 2.0, "unit": "clove"},
                                              {"name": "onion", "quantity": 1.0, "unit": None},
                                              {"name": "salt", "quantity": None, "unit": None}],
                              "tags": ["soup", "vegan"], "calories": 320, "minutes": 35, "notes": "", "created": "2026-10-13",
                              "times_cooked": 0, "last_cooked": None}]

    def test_output(self, planner):
        out = planner.dispatch_tool("add_recipe", SOUP)
        assert out.startswith("Recipe added: Lentil soup (serves 4; 35 min; 320 cal each; tags: soup, vegan) [id=")

    def test_default_servings(self, planner):
        planner.dispatch_tool("add_recipe", {"name": "x", "ingredients": ["a"]})
        assert recipes()[0]["servings"] == 2

    @pytest.mark.parametrize("kw,msg", [
        ({"name": ""}, "needs a name"), ({"name": "n" * 81}, "at most 80"), ({"ingredients": []}, "needs ingredients"),
        ({"ingredients": None}, "needs ingredients"), ({"ingredients": ["ok", ""]}, "needs a name"),
        ({"ingredients": ["a"] * 41}, "at most 40"), ({"servings": 0}, "servings must be a whole number"),
        ({"servings": 101}, "servings must be a whole number"), ({"servings": 2.5}, "servings must be a whole number"),
        ({"servings": True}, "servings must be a whole number"), ({"steps": [1]}, "steps must be a list"),
        ({"steps": ["s"] * 31}, "at most 30 steps"), ({"steps": ["s" * 301]}, "at most 300"),
        ({"tags": ["t" * 21]}, "at most 20"), ({"tags": [f"t{i}" for i in range(9)]}, "at most 8 tags"), ({"tags": 5}, "tags must be"),
        ({"calories_per_serving": 0}, "calories must be"), ({"calories_per_serving": 6000}, "calories must be"),
        ({"minutes": 2000}, "minutes must be"), ({"notes": 5}, "notes must be text")])
    def test_rejected_and_nothing_stored(self, planner, kw, msg):
        out = planner.dispatch_tool("add_recipe", {**SOUP, **kw})
        assert out.startswith("Recipe not added: ") and msg in out, out
        assert recipes() == []

    def test_duplicate_name_and_limit(self, planner, monkeypatch):
        import recipes as r
        recipe(planner)
        assert "already a recipe called 'lentil soup'" in planner.dispatch_tool("add_recipe", {**SOUP, "name": "lentil soup"})
        monkeypatch.setattr(r, "MAX_RECIPES", 1)
        assert "already have 1 recipes" in planner.dispatch_tool("add_recipe", {**SOUP, "name": "other"})

    def test_get_recipe_scaled(self, planner):
        recipe(planner)
        out = planner.dispatch_tool("get_recipe", {"recipe": "lentil", "servings": 8})
        assert out.split("\n")[1:7] == ["Scaled from 4 to 8 servings.", "Ingredients:", "- 400 g red lentils", "- 4 cloves garlic",
                                       "- 2 onion", "- salt"]
        assert out.endswith("Steps:\n1. Chop\n2. Simmer 25 min")

    def test_get_recipe_unscaled_has_no_scaling_line(self, planner):
        recipe(planner)
        out = planner.dispatch_tool("get_recipe", {"recipe": "lentil"})
        assert "Scaled" not in out and "- 200 g red lentils" in out and "- 2 cloves garlic" in out
        assert "Scaled" not in planner.dispatch_tool("get_recipe", {"recipe": "lentil", "servings": 4})

    def test_one_clove_is_singular(self, planner):
        recipe(planner, name="g", servings=2, ingredients=["1 clove garlic"])
        assert "- 1 clove garlic" in planner.dispatch_tool("get_recipe", {"recipe": "g"})
        assert "- 3 cloves garlic" in planner.dispatch_tool("get_recipe", {"recipe": "g", "servings": 6})

    @pytest.mark.parametrize("servings", [0, 101, "x", 2.5])
    def test_bad_scale(self, planner, servings):
        recipe(planner)
        assert planner.dispatch_tool("get_recipe", {"recipe": "lentil", "servings": servings}).startswith("Cannot show the recipe: ")

    def test_resolve(self, planner):
        recipe(planner); recipe(planner, name="Lentil salad")
        assert "matches 2 recipes" in planner.dispatch_tool("get_recipe", {"recipe": "lentil"})
        assert planner.dispatch_tool("get_recipe", {"recipe": "lentil soup"}).startswith("Lentil soup")
        assert "no recipe matches 'pizza'" in planner.dispatch_tool("get_recipe", {"recipe": "pizza"})
        assert "say which recipe" in planner.dispatch_tool("get_recipe", {"recipe": ""})

    def test_list_filters(self, planner):
        recipe(planner); recipe(planner, **OMELETTE, tags=["quick"])
        assert planner.dispatch_tool("get_recipes", {}).startswith("2 recipes:")
        assert planner.dispatch_tool("get_recipes", {"tag": "SOUP"}).startswith("1 recipe:\n- Lentil soup")
        assert planner.dispatch_tool("get_recipes", {"query": "eggs"}).startswith("1 recipe:\n- Omelette")
        assert planner.dispatch_tool("get_recipes", {"query": "garlic"}).startswith("1 recipe:\n- Lentil soup")
        assert planner.dispatch_tool("get_recipes", {"tag": "dessert"}) == "No recipes match."
        assert planner.dispatch_tool("get_recipes", {"limit": 1}).startswith("1 recipe:")
        assert planner.dispatch_tool("get_recipes", {"limit": 0}).startswith("Cannot list recipes: ")

    def test_empty_list(self, planner):
        assert planner.dispatch_tool("get_recipes", {}) == "No recipes yet. Add one with add_recipe."


class TestUpdateDelete:
    def test_update(self, planner):
        recipe(planner)
        out = planner.dispatch_tool("update_recipe", {"recipe": "lentil", "fields": {
            "name": "Red lentil soup", "servings": 6, "ingredients": ["300 g lentils"], "steps": "Boil", "tags": "soup",
            "calories": 300, "minutes": "", "notes": "good"}})
        assert out.startswith("Recipe updated: Red lentil soup (serves 6; 300 cal each; tags: soup)")
        r = recipes()[0]
        assert r["ingredients"] == [{"name": "lentils", "quantity": 300.0, "unit": "g"}] and r["steps"] == ["Boil"] and r["minutes"] is None

    def test_update_is_all_or_nothing(self, planner):
        recipe(planner)
        out = planner.dispatch_tool("update_recipe", {"recipe": "lentil", "fields": {"name": "New", "servings": 0}})
        assert "servings must be" in out and recipes()[0]["name"] == "Lentil soup"

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"color": 1}, "cannot change color"),
                                            ({"ingredients": []}, "needs ingredients")])
    def test_update_rejected(self, planner, fields, msg):
        recipe(planner)
        assert msg in planner.dispatch_tool("update_recipe", {"recipe": "lentil", "fields": fields})

    def test_rename_into_existing_name(self, planner):
        recipe(planner); recipe(planner, **OMELETTE)
        assert "already a recipe called 'OMELETTE'" in planner.dispatch_tool("update_recipe", {"recipe": "lentil", "fields": {"name": "OMELETTE"}})

    def test_rename_updates_planned_meals(self, planner):
        recipe(planner)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil"})
        planner.dispatch_tool("update_recipe", {"recipe": "lentil", "fields": {"name": "Soup"}})
        assert plan()[0]["name"] == "Soup"

    def test_delete_unlinks_planned_meals(self, planner):
        recipe(planner)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil", "repeat_days": 2})
        out = planner.dispatch_tool("delete_recipe", {"recipe": "lentil"})
        assert out == "Deleted recipe Lentil soup. This can't be undone. 2 planned meal(s) stay in the plan as plain text."
        assert recipes() == [] and [m["recipe_id"] for m in plan()] == [None, None] and plan()[0]["name"] == "Lentil soup"

    def test_delete_without_plan(self, planner):
        recipe(planner)
        assert planner.dispatch_tool("delete_recipe", {"recipe": "lentil"}) == "Deleted recipe Lentil soup. This can't be undone."


class TestSuggest:
    def test_never_cooked_then_oldest(self, planner):
        import storage
        recipe(planner); recipe(planner, **OMELETTE, tags=["quick"]); recipe(planner, name="Pasta", ingredients=["pasta"], minutes=15, tags=["quick"])
        rows = storage.load_recipes()
        rows[0]["last_cooked"], rows[0]["times_cooked"] = "2026-10-01", 1
        rows[1]["last_cooked"], rows[1]["times_cooked"] = "2026-09-01", 1
        storage.save_recipes(rows)
        out = planner.dispatch_tool("suggest_recipes", {})
        assert out.startswith("3 recipes to cook next:") and out.index("Pasta") < out.index("Omelette") < out.index("Lentil soup")

    def test_filters_and_limit(self, planner):
        recipe(planner); recipe(planner, **OMELETTE, tags=["quick"])
        assert planner.dispatch_tool("suggest_recipes", {"max_minutes": 10}).startswith("1 recipe to cook next:\n- Omelette")
        assert planner.dispatch_tool("suggest_recipes", {"tag": "soup"}).startswith("1 recipe to cook next:\n- Lentil soup")
        assert planner.dispatch_tool("suggest_recipes", {"limit": 1}).startswith("1 recipe to cook next:")
        assert planner.dispatch_tool("suggest_recipes", {"max_minutes": 5}).startswith("No recipe fits")
        assert planner.dispatch_tool("suggest_recipes", {"limit": 11}).startswith("Cannot suggest recipes: ")


class TestPlanMeal:
    def test_recipe_meal(self, planner):
        recipe(planner)
        out = planner.dispatch_tool("plan_meal", {"slot": "Dinner", "recipe": "lentil"})
        assert out.startswith("Planned for 2026-10-13: dinner: Lentil soup (4 servings, 320 cal per serving) [id=")
        m = plan()[0]
        assert (m["date"], m["slot"], m["servings"], m["calories"], m["eaten"]) == ("2026-10-13", "dinner", 4, 320, False)

    def test_text_meal_and_servings(self, planner):
        out = planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": " leftovers ", "date": "tomorrow"})
        assert out.startswith("Planned for 2026-10-14: lunch: leftovers (1 serving) [id=")
        recipe(planner)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil", "servings": 2})
        assert plan()[1]["servings"] == 2

    def test_repeat_days(self, planner):
        recipe(planner)
        out = planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil", "repeat_days": 3, "date": "friday"})
        assert out == "Planned on 3 days (2026-10-16 to 2026-10-18): dinner: Lentil soup (4 servings each day)"
        assert [m["date"] for m in plan()] == ["2026-10-16", "2026-10-17", "2026-10-18"]

    @pytest.mark.parametrize("kw,msg", [
        ({}, "either a recipe or some text"), ({"text": "x", "recipe": "lentil"}, "either a recipe or some text"),
        ({"text": "x", "slot": "brunch"}, "slot must be one of"), ({"text": "x", "slot": None}, "slot must be one of"),
        ({"text": "x", "date": "never"}, "couldn't understand"), ({"text": "x", "date": "2028-01-01"}, "within 365 days"),
        ({"recipe": "pizza"}, "no recipe matches"), ({"text": "x", "servings": 0}, "servings must be"),
        ({"text": "x", "repeat_days": 15}, "repeat_days must be"), ({"text": "x" * 81}, "at most 80"),
        ({"text": "x", "repeat_days": 0}, "repeat_days must be")])
    def test_rejected_and_nothing_stored(self, planner, kw, msg):
        recipe(planner)
        out = planner.dispatch_tool("plan_meal", {"slot": "dinner", **kw})
        assert out.startswith("Meal not planned: ") and msg in out, out
        assert plan() == []

    def test_repeat_past_the_date_range_adds_nothing(self, planner):
        out = planner.dispatch_tool("plan_meal", {"slot": "dinner", "text": "x", "date": "2027-10-13", "repeat_days": 3})
        assert "within 365 days" in out and plan() == []

    def test_per_day_and_total_limits(self, planner, monkeypatch):
        import recipes as r
        monkeypatch.setattr(r, "MAX_MEALS_PER_DAY", 2)
        for _ in range(2):
            planner.dispatch_tool("plan_meal", {"slot": "snack", "text": "fruit"})
        assert "already has 2 planned meals" in planner.dispatch_tool("plan_meal", {"slot": "snack", "text": "nuts"})
        assert "already has 2" in planner.dispatch_tool("plan_meal", {"slot": "snack", "text": "nuts", "repeat_days": 2})
        assert len(plan()) == 2
        monkeypatch.setattr(r, "MAX_MEALS", 2)
        assert "meal plan is full" in planner.dispatch_tool("plan_meal", {"slot": "snack", "text": "nuts", "date": "friday"})

    def test_plan_view(self, planner):
        recipe(planner)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil"})
        planner.dispatch_tool("plan_meal", {"slot": "breakfast", "text": "oats", "date": "tomorrow"})
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "text": "pizza", "date": "tomorrow"})
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "soup", "date": "tomorrow"})
        out = planner.dispatch_tool("get_meal_plan", {"days": 3}).split("\n")
        assert out[0] == "Meal plan 2026-10-13 to 2026-10-15: 4 meals."
        assert out[1:3] == ["Tue 2026-10-13", out[2]] and out[2].startswith("  dinner: Lentil soup (4 servings, 320 cal per serving) [id=")
        assert [l.split(":")[0].strip() for l in out[3:8]] == ["Wed 2026-10-14", "breakfast", "lunch", "dinner", "Thu 2026-10-15"]
        assert out[-1] == "  nothing planned"

    def test_plan_view_empty_and_bad(self, planner):
        assert planner.dispatch_tool("get_meal_plan", {}) == "No meals planned from 2026-10-13 to 2026-10-19. Add one with plan_meal."
        assert planner.dispatch_tool("get_meal_plan", {"days": 32}).startswith("Cannot show the meal plan: ")
        assert planner.dispatch_tool("get_meal_plan", {"days": 31}).startswith("No meals planned from 2026-10-13 to 2026-11-12")

    def test_clear_by_id_day_and_slot(self, planner):
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "text": "a"})
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "b"})
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "c", "date": "tomorrow"})
        assert planner.dispatch_tool("clear_meals", {"date": "today", "slot": "lunch"}).startswith("Cleared 1 planned meal: 2026-10-13 lunch b")
        assert planner.dispatch_tool("clear_meals", {"meal": plan()[0]["id"].upper()}).startswith("Cleared 1 planned meal: 2026-10-13 dinner a")
        assert planner.dispatch_tool("clear_meals", {"date": "tomorrow"}).startswith("Cleared 1 planned meal")
        assert plan() == []

    @pytest.mark.parametrize("kw,msg", [({}, "give a meal id, or a date"), ({"meal": "zzz"}, "no planned meal has the id"),
                                        ({"date": "tomorrow"}, "nothing is planned for 2026-10-14"),
                                        ({"date": "tomorrow", "slot": "lunch"}, "nothing is planned for 2026-10-14 lunch"),
                                        ({"date": "today", "slot": "brunch"}, "slot must be one of")])
    def test_clear_rejected(self, planner, kw, msg):
        assert msg in planner.dispatch_tool("clear_meals", kw) and plan() == []


class TestLogPlannedMeal:
    def test_logs_one_portion_by_default(self, planner):
        recipe(planner)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil"})
        out = planner.dispatch_tool("log_planned_meal", {"meal": "lentil"})
        assert out.startswith("Logged planned meal as eaten: dinner: Lentil soup (4 servings, 320 cal per serving, eaten)")
        assert "Meal logged: Lentil soup (320 cal)" in out
        import storage
        n = storage.load_nutrition()
        assert len(n) == 1 and n[0]["calories"] == 320 and n[0]["time"] == "dinner" and n[0]["date"] == "2026-10-13"
        assert plan()[0]["eaten"] is True
        r = recipes()[0]
        assert (r["times_cooked"], r["last_cooked"]) == (1, "2026-10-13")

    def test_portions(self, planner):
        recipe(planner)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil"})
        planner.dispatch_tool("log_planned_meal", {"meal": "dinner", "portions": 1.5})
        import storage
        assert storage.load_nutrition()[0]["calories"] == 480

    @pytest.mark.parametrize("portions", [0, 0.1, 21, "x", True])
    def test_bad_portions(self, planner, portions):
        recipe(planner)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil"})
        assert "portions must be" in planner.dispatch_tool("log_planned_meal", {"meal": "lentil", "portions": portions})
        assert plan()[0]["eaten"] is False

    def test_text_meal_without_calories(self, planner):
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "leftovers"})
        out = planner.dispatch_tool("log_planned_meal", {"meal": "leftovers"})
        assert "Meal logged: leftovers (0 cal)" in out and recipes() == []

    def test_twice_is_rejected(self, planner):
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "leftovers"})
        planner.dispatch_tool("log_planned_meal", {"meal": "leftovers"})
        assert "already logged as eaten" in planner.dispatch_tool("log_planned_meal", {"meal": plan()[0]["id"]})
        import storage
        assert len(storage.load_nutrition()) == 1

    def test_future_meals_cannot_be_logged(self, planner):
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "leftovers", "date": "tomorrow"})
        out = planner.dispatch_tool("log_planned_meal", {"meal": plan()[0]["id"]})
        assert out.startswith("Not logged: ") and plan()[0]["eaten"] is False
        import storage
        assert storage.load_nutrition() == []

    def test_a_past_meal_is_backdated(self, planner):
        recipe(planner)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil", "date": "2026-10-11"})
        planner.dispatch_tool("log_planned_meal", {"meal": "lentil", "date": "2026-10-11"})
        import storage
        assert storage.load_nutrition()[0]["date"] == "2026-10-11" and recipes()[0]["last_cooked"] == "2026-10-11"

    def test_last_cooked_never_goes_backwards(self, planner):
        import storage
        recipe(planner)
        rows = storage.load_recipes(); rows[0]["last_cooked"] = "2026-10-12"; storage.save_recipes(rows)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil", "date": "2026-10-10"})
        planner.dispatch_tool("log_planned_meal", {"meal": "lentil", "date": "2026-10-10"})
        assert recipes()[0]["last_cooked"] == "2026-10-12"

    def test_ambiguity_and_unknowns(self, planner):
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "soup"})
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "text": "soup"})
        assert "matches 2 meals on 2026-10-13" in planner.dispatch_tool("log_planned_meal", {"meal": "soup"})
        assert planner.dispatch_tool("log_planned_meal", {"meal": "lunch"}).startswith("Logged planned meal")
        assert "no planned meal matches 'pizza'" in planner.dispatch_tool("log_planned_meal", {"meal": "pizza"})
        assert "say which planned meal" in planner.dispatch_tool("log_planned_meal", {"meal": ""})

    def test_an_eaten_duplicate_name_picks_the_pending_one(self, planner):
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "soup"})
        planner.dispatch_tool("log_planned_meal", {"meal": "soup"})
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "text": "soup"})
        assert planner.dispatch_tool("log_planned_meal", {"meal": "soup"}).startswith("Logged planned meal as eaten: dinner: soup")


class TestShopping:
    def setup(self, planner):
        recipe(planner)
        recipe(planner, **OMELETTE)
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "lentil"})
        planner.dispatch_tool("plan_meal", {"slot": "breakfast", "recipe": "omelette", "date": "tomorrow", "servings": 3})

    def shopping(self):
        import storage
        return [(r["text"], r["quantity"], r["list"]) for r in storage.load_lists()]

    def test_adds_up_and_scales(self, planner):
        self.setup(planner)
        out = planner.dispatch_tool("shopping_from_plan", {"days": 3})
        assert out.startswith("Added 6 item(s) to the shopping list for 2 planned meal(s) from 2026-10-13 to 2026-10-15.")
        assert dict((t, q) for t, q, _ in self.shopping()) == {"eggs": "6", "garlic": "2 cloves", "olive oil": "3 tbsp", "onion": "1",
                                                              "red lentils": "200 g", "salt": None}

    def test_same_ingredient_in_two_meals(self, planner):
        self.setup(planner)
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "recipe": "lentil", "date": "tomorrow", "servings": 8})
        planner.dispatch_tool("shopping_from_plan", {"days": 3})
        q = dict((t, q) for t, q, _ in self.shopping())
        assert q["red lentils"] == "600 g" and q["garlic"] == "6 cloves" and q["salt"] is None

    def test_different_units_of_one_ingredient_share_a_line(self, planner):
        recipe(planner, name="a", servings=2, ingredients=["200 ml milk"])
        recipe(planner, name="b", servings=2, ingredients=["2 cups milk", "milk"])
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "recipe": "a", "servings": 2})
        planner.dispatch_tool("plan_meal", {"slot": "dinner", "recipe": "b", "servings": 2})
        planner.dispatch_tool("shopping_from_plan", {"days": 1})
        assert self.shopping() == [("milk", "200 ml + 2 cups", "shopping")]

    def test_skip_other_list_and_eaten(self, planner):
        self.setup(planner)
        planner.dispatch_tool("log_planned_meal", {"meal": "lentil"})
        out = planner.dispatch_tool("shopping_from_plan", {"days": 3, "list": "Weekend", "skip": ["Salt", "olive OIL"]})
        assert "Added 1 item(s) to the weekend list for 1 planned meal(s)" in out
        assert self.shopping() == [("eggs", "6", "weekend")]
        planner.dispatch_tool("clear_checked_items", {})
        out = planner.dispatch_tool("shopping_from_plan", {"days": 3, "include_eaten": True, "list": "other"})
        assert "for 2 planned meal(s)" in out

    def test_items_already_on_the_list_are_left_alone(self, planner):
        self.setup(planner)
        planner.dispatch_tool("add_list_items", {"items": "eggs"})
        out = planner.dispatch_tool("shopping_from_plan", {"days": 3})
        assert "Already on the list (left as they are): eggs" in out
        assert ("eggs", None, "shopping") in self.shopping() and len([1 for t, _, _ in self.shopping() if t == "eggs"]) == 1

    def test_meals_without_a_recipe_are_reported(self, planner):
        self.setup(planner)
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "leftovers"})
        planner.dispatch_tool("plan_meal", {"slot": "snack", "text": "fruit"})
        out = planner.dispatch_tool("shopping_from_plan", {"days": 3})
        assert out.endswith("Not included (no recipe): leftovers, fruit")

    def test_nothing_to_buy(self, planner):
        out = planner.dispatch_tool("shopping_from_plan", {})
        assert out.startswith("Nothing added to the list: nothing to buy") and self.shopping() == []
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "text": "leftovers"})
        assert "nothing to buy" in planner.dispatch_tool("shopping_from_plan", {})

    def test_deleted_recipe_is_not_bought(self, planner):
        self.setup(planner)
        planner.dispatch_tool("delete_recipe", {"recipe": "omelette"})
        planner.dispatch_tool("shopping_from_plan", {"days": 3})
        assert "eggs" not in [t for t, _, _ in self.shopping()]

    def test_range_respected(self, planner):
        self.setup(planner)
        planner.dispatch_tool("shopping_from_plan", {"days": 1})
        assert "eggs" not in [t for t, _, _ in self.shopping()] and "onion" in [t for t, _, _ in self.shopping()]
        planner.dispatch_tool("shopping_from_plan", {"date": "tomorrow", "days": 1})
        assert "eggs" in [t for t, _, _ in self.shopping()]

    @pytest.mark.parametrize("kw,msg", [({"days": 0}, "days must be"), ({"days": 32}, "days must be"), ({"skip": "salt"}, "skip must be a list"),
                                        ({"skip": [1]}, "skip must be a list"), ({"include_eaten": "yes"}, "include_eaten must be"),
                                        ({"list": "l" * 41}, "at most 40"), ({"date": "never"}, "couldn't understand")])
    def test_bad_arguments_change_nothing(self, planner, kw, msg):
        self.setup(planner)
        out = planner.dispatch_tool("shopping_from_plan", kw)
        assert out.startswith("Nothing added to the list: ") and msg in out and self.shopping() == []

    def test_a_full_list_is_refused_before_anything_is_added(self, planner, monkeypatch):
        import lists
        self.setup(planner)
        monkeypatch.setattr(lists, "MAX_ITEMS_TOTAL", 3)
        out = planner.dispatch_tool("shopping_from_plan", {"days": 3})
        assert "lists are full" in out and self.shopping() == []

    def test_too_many_ingredients(self, planner, monkeypatch):
        import recipes as r
        self.setup(planner)
        monkeypatch.setattr(r, "MAX_SHOPPING_ITEMS", 2)
        assert "different ingredients" in planner.dispatch_tool("shopping_from_plan", {"days": 3}) and self.shopping() == []

    def test_long_quantity_text_is_shortened(self, planner):
        r1 = [f"{i} {u} milk" for i, u in enumerate(("g", "kg", "ml", "l", "tsp", "tbsp", "cup", "oz"), 1)]
        recipe(planner, name="many", ingredients=r1, servings=1)
        planner.dispatch_tool("plan_meal", {"slot": "lunch", "recipe": "many"})
        planner.dispatch_tool("shopping_from_plan", {"days": 1})
        q = self.shopping()[0][1]
        assert len(q) <= 30 and q.endswith("...")

    def test_damaged_plan_rows_are_ignored(self, planner):
        import storage
        self.setup(planner)
        storage.save_mealplan(storage.load_mealplan() + ["x", None, {"id": "z", "date": "nope", "slot": "dinner"}, {"id": "y", "date": "2026-10-13", "slot": "brunch", "name": "x"}])
        assert planner.dispatch_tool("shopping_from_plan", {"days": 3}).startswith("Added 6 item(s)")
        assert planner.dispatch_tool("get_meal_plan", {"days": 3}).startswith("Meal plan 2026-10-13 to 2026-10-15: 2 meals.")


class TestDamagedRecipes:
    def test_everything_survives_odd_rows(self, planner):
        import storage
        storage.save_recipes(["x", None, {"id": "a", "name": "odd", "ingredients": "no", "servings": "many", "steps": 5, "tags": None},
                              {"id": "b", "name": "odd2", "ingredients": [None, {"name": ""}, {"name": "ok", "quantity": "x"}], "servings": 0}])
        assert planner.dispatch_tool("get_recipes", {}).startswith("2 recipes:")
        assert planner.dispatch_tool("get_recipe", {"recipe": "odd"}).startswith("odd (serves 2)")
        assert "- ok" in planner.dispatch_tool("get_recipe", {"recipe": "odd2", "servings": 4})
        assert planner.dispatch_tool("get_recipes", {"query": "ok"}).startswith("1 recipe:")
        assert planner.dispatch_tool("suggest_recipes", {}).startswith("2 recipes to cook next:")
