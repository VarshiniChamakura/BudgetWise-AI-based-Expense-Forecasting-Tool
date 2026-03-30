from flask import Flask, render_template, request, jsonify, redirect, session
import mysql.connector
from datetime import date
import pandas as pd
import os

# FIX: Matplotlib backend (VERY IMPORTANT)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "supersecretkey"


# -------------------- DATABASE --------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Root@123",
        database="budgetwise"
    )


# -------------------- HOME --------------------
@app.route("/")
def home():
    return render_template("login.html")


# -------------------- REGISTER --------------------
@app.route("/register", methods=["POST"])
def register():
    email = request.form["email"]
    username = request.form["username"]
    password = request.form["password"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
    if cursor.fetchone():
        return jsonify({"status": "error", "message": "Username already taken"})

    cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
    if cursor.fetchone():
        return jsonify({"status": "error", "message": "Email already taken"})

    cursor.execute(
        "INSERT INTO users (email, username, password) VALUES (%s,%s,%s)",
        (email, username, password)
    )

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"status": "success"})


# -------------------- LOGIN --------------------
@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE username=%s AND password=%s",
        (username, password)
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user:
        session["username"] = username
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "error", "message": "Invalid credentials"})


# -------------------- CHANGE PASSWORD --------------------
@app.route("/change-password")
def change_password_page():
    return render_template("change_password.html")


@app.route("/change_password", methods=["POST"])
def change_password():
    email = request.form["email"]
    new_password = request.form["newPassword"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
    if not cursor.fetchone():
        return jsonify({"status": "error", "message": "Email not found"})

    cursor.execute(
        "UPDATE users SET password=%s WHERE email=%s",
        (new_password, email)
    )

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"status": "success"})


# -------------------- DASHBOARD --------------------
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect("/")

    selected_month = request.args.get("month")
    if not selected_month:
        selected_month = date.today().strftime("%Y-%m")
    current_month = selected_month
    today = date.today()
    today_date = today.strftime("%Y-%m-%d")

    conn = get_db_connection()

    # ---------- MONTHLY BUDGET ----------
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amount FROM monthly_budget
        WHERE username=%s AND month LIKE %s
    """, (session["username"], current_month))

    result = cursor.fetchone()
    monthly_budget = float(result[0]) if result else 0

    # ---------- LOAD EXPENSES ----------
    query = "SELECT * FROM expenses WHERE username=%s"
    df = pd.read_sql(query, conn, params=(session["username"],))

    conn.close()

    if df.empty:
        total_spent = 0
        today_spent = 0
        category_summary = {}
    else:
        df["date"] = pd.to_datetime(df["date"])

        total_spent = df[
            df["date"].dt.strftime("%Y-%m") == current_month
        ]["amount"].sum()

        today_spent = df[
            df["date"].dt.strftime("%Y-%m-%d") == today_date
        ]["amount"].sum()

        # ---------- FIXED CATEGORIES ----------
        categories = [
            "Food", "Transport", "Fuel", "Shopping", "Groceries",
            "Fees", "Bills", "Entertainment", "Health", "Others"
        ]

        category_summary = {cat: 0 for cat in categories}

        for _, row in df.iterrows():
            if row["category"] in category_summary:
                category_summary[row["category"]] += float(row["amount"])

    remaining = monthly_budget - total_spent
    monthly_budget = result[0] if result else 0

    # ---------- PIE CHART ----------
    chart_path = os.path.join("static", "category_chart.png")

    values = list(category_summary.values())

    colors = [
        "#7eabf3", "#0F6749", "#f2cc8b", "#fa0b0b", "#d5fa04",
        "#ae98e2", "#09f5da", "#fa6b05", "#070bf8", "#FD08C4"
    ]

    if sum(values) > 0:
        plt.figure(figsize=(5, 5))
        plt.pie(values, labels=categories, autopct='%1.1f%%', colors=colors)
        plt.title("Spending by Category")
        plt.savefig(chart_path)
        plt.close()
    else:
        if os.path.exists(chart_path):
            os.remove(chart_path)

    return render_template(
        "dashboard.html",
        username=session["username"],
        monthly_budget=monthly_budget,
        total_spent=total_spent,
        today_spent=today_spent,
        remaining=remaining
    )


# -------------------- MONTHLY BUDGET --------------------
@app.route("/monthly-budget", methods=["GET", "POST"])
def monthly_budget():
    if "username" not in session:
        return redirect("/")

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        month = request.form["month"]
        amount = request.form.get("amount")

        cursor.execute("""
            SELECT id FROM monthly_budget
            WHERE username=%s AND month LIKE %s
        """, (session["username"], month))

        if cursor.fetchone():
            cursor.execute("""
                UPDATE monthly_budget
                SET amount=%s
                WHERE username=%s AND month=%s
            """, (amount, session["username"], month))
        else:
            cursor.execute("""
                INSERT INTO monthly_budget (username, month, amount)
                VALUES (%s,%s,%s)
            """, (session["username"], month, amount))

        conn.commit()
        return redirect("/dashboard")

    cursor.close()
    conn.close()

    return render_template("monthly_budget.html", username=session["username"])


# -------------------- ADD EXPENSE --------------------
@app.route("/add-expense", methods=["GET", "POST"])
def add_expense():
    if "username" not in session:
        return redirect("/")

    if request.method == "POST":
        expense_date = request.form["date"]
        amount = request.form["amount"]
        category = request.form["category"]
        description = request.form["notes"]

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO expenses (username, date, amount, category, description)
            VALUES (%s,%s,%s,%s,%s)
        """, (session["username"], expense_date, amount, category, description))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/recent-expenses")

    return render_template("add_expense.html", username=session["username"])


# -------------------- RECENT EXPENSES --------------------
@app.route("/recent-expenses")
def recent_expenses():
    if "username" not in session:
        return redirect("/")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM expenses
        WHERE username=%s
        ORDER BY date DESC
    """, (session["username"],))

    expenses = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("recent_expenses.html",
                           username=session["username"],
                           expenses=expenses)


# -------------------- DELETE EXPENSE --------------------
@app.route("/delete-expense/<int:id>")
def delete_expense(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM expenses WHERE id=%s AND username=%s",
                   (id, session["username"]))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/recent-expenses")


# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True)