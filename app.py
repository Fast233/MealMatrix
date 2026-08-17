import csv
import os
import datetime
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "mealmatrix-school-demo-key"

PROGRAM_FOLDER = os.path.dirname(os.path.abspath(__file__))
FOOD_DATABASE_FILE = os.path.join(PROGRAM_FOLDER, "foods.csv")
MEALS_FILE = os.path.join(PROGRAM_FOLDER, "meals.csv")
GOAL_FILE = os.path.join(PROGRAM_FOLDER, "goal.csv")


def current_date():
    return datetime.date.today().strftime("%d-%m-%Y")


def load_food_database():
    foods = {}
    try:
        with open(FOOD_DATABASE_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                try:
                    if len(row) == 5:
                        foods[row[0].strip().lower()] = {
                            "name": row[0].strip().title(),
                            "calories": float(row[1]),
                            "protein": float(row[2]),
                            "carbs": float(row[3]),
                            "fat": float(row[4]),
                        }
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return foods


def create_files():
    if not os.path.exists(MEALS_FILE):
        with open(MEALS_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "meal_id", "date", "meal_type", "food_item", "quantity",
                "calories", "protein", "carbs", "fat"
            ])
    if not os.path.exists(GOAL_FILE):
        with open(GOAL_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["weekly_goal"], [0]])


def get_meals():
    create_files()
    meals = []
    with open(MEALS_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            meals.append(row)
    return meals


def save_meals(meals):
    fields = ["meal_id", "date", "meal_type", "food_item", "quantity",
              "calories", "protein", "carbs", "fat"]
    with open(MEALS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(meals)


def get_daily_target():
    try:
        with open(GOAL_FILE, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
            return float(rows[1][0]) / 7
    except (FileNotFoundError, IndexError, ValueError):
        return 0


def save_goal(weekly_goal):
    with open(GOAL_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["weekly_goal"], [weekly_goal]])


def nutrition_totals(meals):
    totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for meal in meals:
        for key in totals:
            totals[key] += float(meal[key])
    return {key: round(value, 1) for key, value in totals.items()}


def make_meal(food, meal_type, quantity):
    return {
        "meal_id": str(uuid.uuid4()),
        "date": current_date(),
        "meal_type": meal_type,
        "food_item": food["name"],
        "quantity": str(quantity),
        "calories": str(round(food["calories"] * quantity, 1)),
        "protein": str(round(food["protein"] * quantity, 1)),
        "carbs": str(round(food["carbs"] * quantity, 1)),
        "fat": str(round(food["fat"] * quantity, 1)),
    }


@app.route("/")
def home():
    meals = get_meals()
    today_meals = [m for m in meals if m["date"] == current_date()]
    totals = nutrition_totals(today_meals)
    return render_template("dashboard.html", page="Dashboard", meals=today_meals,
                           totals=totals, target=get_daily_target(), today=current_date())


@app.route("/add-meal", methods=["GET", "POST"])
def add_meal():
    foods = load_food_database()
    if request.method == "POST":
        food_name = request.form.get("food", "").lower()
        meal_type = request.form.get("meal_type", "Breakfast")
        try:
            quantity = float(request.form.get("quantity", "1"))
            if quantity <= 0:
                raise ValueError
        except ValueError:
            flash("Please enter a valid quantity.", "error")
            return redirect(url_for("add_meal"))
        if food_name not in foods:
            flash("Food not found in the database.", "error")
            return redirect(url_for("add_meal"))
        meals = get_meals()
        meals.append(make_meal(foods[food_name], meal_type, quantity))
        save_meals(meals)
        flash("Meal added successfully.", "success")
        return redirect(url_for("home"))
    return render_template("add_meal.html", page="Add Meal", foods=sorted(foods.values(), key=lambda x: x["name"]))


@app.route("/meals")
def meals():
    all_meals = list(reversed(get_meals()))
    query = request.args.get("q", "").strip().lower()
    if query:
        all_meals = [m for m in all_meals if query in m["food_item"].lower() or query in m["meal_type"].lower()]
    return render_template("meals.html", page="Search Meals", meals=all_meals, query=query)


@app.route("/foods")
def foods():
    data = sorted(load_food_database().values(), key=lambda x: x["name"])
    query = request.args.get("q", "").strip().lower()
    if query:
        data = [f for f in data if query in f["name"].lower()]
    return render_template("foods.html", page="Food Database", foods=data, query=query)


@app.route("/goal", methods=["GET", "POST"])
def goal():
    if request.method == "POST":
        try:
            weekly = float(request.form["weekly_goal"])
            if weekly < 0:
                raise ValueError
            save_goal(weekly)
            flash("Weekly goal saved.", "success")
        except ValueError:
            flash("Enter a valid non-negative goal.", "error")
        return redirect(url_for("goal"))
    return render_template("goal.html", page="Calorie Goal", target=get_daily_target())


@app.route("/report")
def report():
    meals = get_meals()
    dates = sorted({m["date"] for m in meals}, key=lambda d: datetime.datetime.strptime(d, "%d-%m-%Y"))[-7:]
    rows = []
    for date in dates:
        day_meals = [m for m in meals if m["date"] == date]
        rows.append({"date": date, **nutrition_totals(day_meals)})
    return render_template("report.html", page="Weekly Report", rows=rows)


@app.route("/suggestions")
def suggestions():
    meals = get_meals()
    counts = {}
    for meal in meals:
        counts[meal["food_item"]] = counts.get(meal["food_item"], 0) + 1
    top_food = max(counts, key=counts.get) if counts else None
    recent = meals[-7:]
    recent_totals = nutrition_totals(recent)
    tips = []
    if not meals:
        tips.append("Log a few normal meals first. The suggestion system needs your real eating pattern before it can personalise advice.")
    else:
        tips.append(f"You record {top_food} most often ({counts[top_food]} time(s)). Consider adding variety around foods you already enjoy.")
        if len({m['meal_type'] for m in meals}) < 3:
            tips.append("Your log currently covers a small range of meal types. Logging meals as they happen will make pattern analysis more useful.")
        tips.append(f"Your latest seven meal records contain {recent_totals['calories']} kcal in total according to the food database.")
    return render_template("suggestions.html", page="AI Coach", tips=tips, top_food=top_food, meal_count=len(meals))


@app.route("/habits")
def habits():
    meals = get_meals()
    counts = {}
    for m in meals:
        counts[m["food_item"]] = counts.get(m["food_item"], 0) + 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]
    return render_template("habits.html", page="Food Habits", ranked=ranked, meal_count=len(meals))


@app.route("/delete/<meal_id>", methods=["POST"])
def delete_meal(meal_id):
    meals = [m for m in get_meals() if m["meal_id"] != meal_id]
    save_meals(meals)
    flash("Meal removed.", "success")
    return redirect(request.referrer or url_for("home"))


if __name__ == "__main__":
    create_files()
    app.run(debug=True)
