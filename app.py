import csv
import os
import sqlite3
import datetime
import uuid

from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

# Use an environment variable in production.
# The fallback is only for local development.
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "mealmatrix-development-key"
)

PROGRAM_FOLDER = os.path.dirname(
    os.path.abspath(__file__)
)

FOOD_DATABASE_FILE = os.path.join(
    PROGRAM_FOLDER,
    "foods.csv"
)

DATABASE_FILE = os.path.join(
    PROGRAM_FOLDER,
    "mealmatrix.db"
)


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DATABASE_FILE)

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def create_database():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            age INTEGER,
            height REAL,
            weight REAL,
            goal TEXT,
            activity_level TEXT,
            food_preference TEXT,
            meals_per_day INTEGER,
            meal_times TEXT,
            activity_frequency TEXT,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS meals (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            food_item TEXT NOT NULL,
            quantity REAL NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL NOT NULL,
            fat REAL NOT NULL,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS custom_foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL NOT NULL,
            fat REAL NOT NULL,
            UNIQUE(user_id, name),
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            weekly_goal REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );
    """)

    conn.commit()
    conn.close()


# ============================================================
# HELPERS
# ============================================================

def current_date():
    return datetime.date.today().strftime("%d-%m-%Y")


def current_user_id():
    return session.get("user_id")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if not current_user_id():
            flash(
                "Please sign in to continue.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapped_view


def get_current_user():
    user_id = current_user_id()

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute(
        """
        SELECT id, name, email, created_at
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return user


# ============================================================
# BUILT-IN FOOD DATABASE
# ============================================================

def load_food_database():
    foods = {}

    try:

        with open(
            FOOD_DATABASE_FILE,
            "r",
            newline="",
            encoding="utf-8"
        ) as f:

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
                            "fat": float(row[4])
                        }

                except ValueError:
                    pass

    except FileNotFoundError:
        pass

    return foods


def load_user_foods(user_id):

    foods = load_food_database()

    conn = get_db()

    rows = conn.execute(
        """
        SELECT name, calories, protein, carbs, fat
        FROM custom_foods
        WHERE user_id = ?
        ORDER BY name
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    for row in rows:

        foods[row["name"].lower()] = {
            "name": row["name"],
            "calories": row["calories"],
            "protein": row["protein"],
            "carbs": row["carbs"],
            "fat": row["fat"]
        }

    return foods


# ============================================================
# MEALS
# ============================================================

def get_meals(user_id):

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            id AS meal_id,
            date,
            meal_type,
            food_item,
            quantity,
            calories,
            protein,
            carbs,
            fat
        FROM meals
        WHERE user_id = ?
        ORDER BY rowid ASC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def save_meal(
    user_id,
    food,
    meal_type,
    quantity
):

    meal_id = str(uuid.uuid4())

    conn = get_db()

    conn.execute(
        """
        INSERT INTO meals (
            id,
            user_id,
            date,
            meal_type,
            food_item,
            quantity,
            calories,
            protein,
            carbs,
            fat
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            meal_id,
            user_id,
            current_date(),
            meal_type,
            food["name"],
            quantity,
            round(food["calories"] * quantity, 1),
            round(food["protein"] * quantity, 1),
            round(food["carbs"] * quantity, 1),
            round(food["fat"] * quantity, 1)
        )
    )

    conn.commit()
    conn.close()


def nutrition_totals(meals):

    totals = {
        "calories": 0,
        "protein": 0,
        "carbs": 0,
        "fat": 0
    }

    for meal in meals:

        for key in totals:

            totals[key] += float(
                meal[key]
            )

    return {
        key: round(value, 1)
        for key, value in totals.items()
    }


# ============================================================
# GOALS
# ============================================================

def get_daily_target(user_id):

    conn = get_db()

    row = conn.execute(
        """
        SELECT weekly_goal
        FROM goals
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    if not row:
        return 0

    return round(
        float(row["weekly_goal"]) / 7,
        1
    )


def save_goal(
    user_id,
    weekly_goal
):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO goals (
            user_id,
            weekly_goal
        )
        VALUES (?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET
            weekly_goal = excluded.weekly_goal
        """,
        (
            user_id,
            weekly_goal
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# PROFILE
# ============================================================

def get_profile(user_id):

    conn = get_db()

    profile = conn.execute(
        """
        SELECT *
        FROM profiles
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return profile


def save_profile(
    user_id,
    age,
    height,
    weight,
    goal,
    activity_level,
    food_preference,
    meals_per_day,
    meal_times,
    activity_frequency
):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO profiles (
            user_id,
            age,
            height,
            weight,
            goal,
            activity_level,
            food_preference,
            meals_per_day,
            meal_times,
            activity_frequency
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET
            age = excluded.age,
            height = excluded.height,
            weight = excluded.weight,
            goal = excluded.goal,
            activity_level = excluded.activity_level,
            food_preference = excluded.food_preference,
            meals_per_day = excluded.meals_per_day,
            meal_times = excluded.meal_times,
            activity_frequency = excluded.activity_frequency
        """,
        (
            user_id,
            age,
            height,
            weight,
            goal,
            activity_level,
            food_preference,
            meals_per_day,
            meal_times,
            activity_frequency
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# PUBLIC LANDING PAGE
# ============================================================

@app.route("/")
def landing():

    if current_user_id():
        return redirect(
            url_for("home")
        )

    return render_template(
        "landing.html",
        page="Home"
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if current_user_id():
        return redirect(
            url_for("home")
        )

    if request.method == "POST":

        # register.html uses "username"
        # Database column remains "name"
        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if not username or not email or not password:

            flash(
                "Please complete all required fields.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 8:

            flash(
                "Password must be at least 8 characters.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        conn = get_db()

        existing = conn.execute(
            """
            SELECT id
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if existing:

            conn.close()

            flash(
                "An account with that email already exists.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        password_hash = generate_password_hash(
            password
        )

        cursor = conn.execute(
            """
            INSERT INTO users (
                name,
                email,
                password_hash,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                email,
                password_hash,
                datetime.datetime.now().isoformat()
            )
        )

        user_id = cursor.lastrowid

        conn.execute(
            """
            INSERT INTO goals (
                user_id,
                weekly_goal
            )
            VALUES (?, 0)
            """,
            (user_id,)
        )

        conn.commit()
        conn.close()

        session.clear()

        session["user_id"] = user_id

        return redirect(
            url_for("profile_setup")
        )

    return render_template(
        "register.html",
        page="Register"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if current_user_id():
        return redirect(
            url_for("home")
        )

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        conn.close()

        if not user or not check_password_hash(
            user["password_hash"],
            password
        ):

            flash(
                "Incorrect email or password.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        session.clear()

        session["user_id"] = user["id"]

        profile = get_profile(
            user["id"]
        )

        if profile is None:

            return redirect(
                url_for("profile_setup")
            )

        return redirect(
            url_for("home")
        )

    return render_template(
        "login.html",
        page="Sign In"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been signed out.",
        "success"
    )

    return redirect(
        url_for("landing")
    )


# ============================================================
# PROFILE SETUP
# ============================================================

@app.route(
    "/profile/setup",
    methods=["GET", "POST"]
)
@login_required
def profile_setup():

    user = get_current_user()

    if request.method == "POST":

        try:

            age = int(
                request.form.get(
                    "age",
                    ""
                )
            )

            height = float(
                request.form.get(
                    "height",
                    ""
                )
            )

            weight = float(
                request.form.get(
                    "weight",
                    ""
                )
            )

            meals_per_day = int(
                request.form.get(
                    "meals_per_day",
                    "3"
                )
            )

        except ValueError:

            flash(
                "Please enter valid numbers.",
                "error"
            )

            return redirect(
                url_for("profile_setup")
            )

        if age <= 0 or height <= 0 or weight <= 0:

            flash(
                "Please enter valid profile information.",
                "error"
            )

            return redirect(
                url_for("profile_setup")
            )

        save_profile(
            user["id"],
            age,
            height,
            weight,
            request.form.get("goal", ""),
            request.form.get(
                "activity_level",
                ""
            ),
            request.form.get(
                "food_preference",
                ""
            ),
            meals_per_day,
            request.form.get(
                "meal_times",
                ""
            ),
            request.form.get(
                "activity_frequency",
                ""
            )
        )

        flash(
            "Your MealMatrix profile is ready.",
            "success"
        )

        return redirect(
            url_for("home")
        )

    return render_template(
        "profile_setup.html",
        page="Build Your Profile",
        user=user,
        profile=get_profile(user["id"])
    )


# ============================================================
# PROFILE
# ============================================================

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
@login_required
def profile():

    user = get_current_user()

    if request.method == "POST":

        try:

            age = int(
                request.form.get(
                    "age",
                    ""
                )
            )

            height = float(
                request.form.get(
                    "height",
                    ""
                )
            )

            weight = float(
                request.form.get(
                    "weight",
                    ""
                )
            )

            meals_per_day = int(
                request.form.get(
                    "meals_per_day",
                    "3"
                )
            )

        except ValueError:

            flash(
                "Please enter valid numbers.",
                "error"
            )

            return redirect(
                url_for("profile")
            )

        save_profile(
            user["id"],
            age,
            height,
            weight,
            request.form.get(
                "goal",
                ""
            ),
            request.form.get(
                "activity_level",
                ""
            ),
            request.form.get(
                "food_preference",
                ""
            ),
            meals_per_day,
            request.form.get(
                "meal_times",
                ""
            ),
            request.form.get(
                "activity_frequency",
                ""
            )
        )

        flash(
            "Profile updated.",
            "success"
        )

        return redirect(
            url_for("profile")
        )

    return render_template(
        "profile.html",
        page="My Profile",
        user=user,
        profile=get_profile(user["id"])
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard_redirect():

    return redirect(
        url_for("home")
    )


@app.route("/app")
@login_required
def home():

    user = get_current_user()

    meals = get_meals(
        user["id"]
    )

    today_meals = [
        m for m in meals
        if m["date"] == current_date()
    ]

    totals = nutrition_totals(
        today_meals
    )

    return render_template(
        "dashboard.html",
        page="Dashboard",
        meals=today_meals,
        totals=totals,
        target=get_daily_target(
            user["id"]
        ),
        today=current_date(),
        user=user,
        profile=get_profile(
            user["id"]
        )
    )


# ============================================================
# ADD MEAL
# ============================================================

@app.route(
    "/add-meal",
    methods=["GET", "POST"]
)
@login_required
def add_meal():

    user = get_current_user()

    foods = load_user_foods(
        user["id"]
    )

    if request.method == "POST":

        food_name = request.form.get(
            "food",
            ""
        ).lower()

        meal_type = request.form.get(
            "meal_type",
            "Breakfast"
        )

        try:

            quantity = float(
                request.form.get(
                    "quantity",
                    "1"
                )
            )

            if quantity <= 0:
                raise ValueError

        except ValueError:

            flash(
                "Please enter a valid quantity.",
                "error"
            )

            return redirect(
                url_for("add_meal")
            )

        if food_name not in foods:

            flash(
                "Food not found in the database.",
                "error"
            )

            return redirect(
                url_for("add_meal")
            )

        save_meal(
            user["id"],
            foods[food_name],
            meal_type,
            quantity
        )

        flash(
            "Meal added successfully.",
            "success"
        )

        return redirect(
            url_for("home")
        )

    return render_template(
        "add_meal.html",
        page="Add Meal",
        foods=sorted(
            foods.values(),
            key=lambda x: x["name"]
        ),
        user=user
    )


# ============================================================
# ADD CUSTOM FOOD
# ============================================================

@app.route(
    "/add-food",
    methods=["POST"]
)
@login_required
def add_food():

    user = get_current_user()

    name = request.form.get(
        "name",
        ""
    ).strip()

    try:

        calories = float(
            request.form.get(
                "calories",
                "0"
            )
        )

        protein = float(
            request.form.get(
                "protein",
                "0"
            )
        )

        carbs = float(
            request.form.get(
                "carbs",
                "0"
            )
        )

        fat = float(
            request.form.get(
                "fat",
                "0"
            )
        )

    except ValueError:

        flash(
            "Please enter valid nutrition values.",
            "error"
        )

        return redirect(
            url_for("add_meal")
        )

    if not name:

        flash(
            "Please enter a food name.",
            "error"
        )

        return redirect(
            url_for("add_meal")
        )

    if min(
        calories,
        protein,
        carbs,
        fat
    ) < 0:

        flash(
            "Nutrition values cannot be negative.",
            "error"
        )

        return redirect(
            url_for("add_meal")
        )

    foods = load_user_foods(
        user["id"]
    )

    if name.lower() in foods:

        flash(
            "That food already exists.",
            "error"
        )

        return redirect(
            url_for("add_meal")
        )

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT INTO custom_foods (
                user_id,
                name,
                calories,
                protein,
                carbs,
                fat
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                name.title(),
                calories,
                protein,
                carbs,
                fat
            )
        )

        conn.commit()

    except sqlite3.IntegrityError:

        flash(
            "That food already exists.",
            "error"
        )

        conn.close()

        return redirect(
            url_for("add_meal")
        )

    conn.close()

    flash(
        f"{name.title()} was added to your food database.",
        "success"
    )

    return redirect(
        url_for("add_meal")
    )


# ============================================================
# MEALS HISTORY
# ============================================================

@app.route("/meals")
@login_required
def meals():

    user = get_current_user()

    all_meals = list(
        reversed(
            get_meals(
                user["id"]
            )
        )
    )

    query = request.args.get(
        "q",
        ""
    ).strip().lower()

    if query:

        all_meals = [
            m for m in all_meals
            if query in m["food_item"].lower()
            or query in m["meal_type"].lower()
        ]

    return render_template(
        "meals.html",
        page="Search Meals",
        meals=all_meals,
        query=query,
        user=user
    )


# ============================================================
# FOOD DATABASE
# ============================================================

@app.route("/foods")
@login_required
def foods():

    user = get_current_user()

    data = sorted(
        load_user_foods(
            user["id"]
        ).values(),
        key=lambda x: x["name"]
    )

    query = request.args.get(
        "q",
        ""
    ).strip().lower()

    if query:

        data = [
            f for f in data
            if query in f["name"].lower()
        ]

    return render_template(
        "foods.html",
        page="Food Database",
        foods=data,
        query=query,
        user=user
    )


# ============================================================
# GOAL
# ============================================================

@app.route(
    "/goal",
    methods=["GET", "POST"]
)
@login_required
def goal():

    user = get_current_user()

    if request.method == "POST":

        try:

            weekly = float(
                request.form[
                    "weekly_goal"
                ]
            )

            if weekly < 0:
                raise ValueError

            save_goal(
                user["id"],
                weekly
            )

            flash(
                "Weekly goal saved.",
                "success"
            )

        except ValueError:

            flash(
                "Enter a valid non-negative goal.",
                "error"
            )

        return redirect(
            url_for("goal")
        )

    return render_template(
        "goal.html",
        page="Calorie Goal",
        target=get_daily_target(
            user["id"]
        ),
        user=user
    )


# ============================================================
# WEEKLY REPORT
# ============================================================

@app.route("/report")
@login_required
def report():

    user = get_current_user()

    meals = get_meals(
        user["id"]
    )

    dates = sorted(
        {
            m["date"]
            for m in meals
        },
        key=lambda d:
            datetime.datetime.strptime(
                d,
                "%d-%m-%Y"
            )
    )[-7:]

    rows = []

    for date in dates:

        day_meals = [
            m for m in meals
            if m["date"] == date
        ]

        rows.append({
            "date": date,
            **nutrition_totals(
                day_meals
            )
        })

    return render_template(
        "report.html",
        page="Weekly Report",
        rows=rows,
        user=user
    )


# ============================================================
# AI COACH — COMING SOON
# ============================================================

@app.route("/suggestions")
@login_required
def suggestions():

    return render_template(
        "suggestions.html",
        page="AI Coach",
        user=get_current_user()
    )


# ============================================================
# FOOD HABITS
# ============================================================

@app.route("/habits")
@login_required
def habits():

    user = get_current_user()

    meals = get_meals(
        user["id"]
    )

    counts = {}

    for m in meals:

        counts[m["food_item"]] = (
            counts.get(
                m["food_item"],
                0
            ) + 1
        )

    ranked = sorted(
        counts.items(),
        key=lambda x: x[1],
        reverse=True
    )[:8]

    return render_template(
        "habits.html",
        page="Food Habits",
        ranked=ranked,
        meal_count=len(meals),
        user=user
    )


# ============================================================
# DELETE MEAL
# ============================================================

@app.route(
    "/delete/<meal_id>",
    methods=["POST"]
)
@login_required
def delete_meal(meal_id):

    user = get_current_user()

    conn = get_db()

    conn.execute(
        """
        DELETE FROM meals
        WHERE id = ?
        AND user_id = ?
        """,
        (
            meal_id,
            user["id"]
        )
    )

    conn.commit()
    conn.close()

    flash(
        "Meal removed.",
        "success"
    )

    return redirect(
        request.referrer
        or url_for("home")
    )


# ============================================================
# STARTUP
# ============================================================

create_database()


if __name__ == "__main__":
    app.run(debug=True)
