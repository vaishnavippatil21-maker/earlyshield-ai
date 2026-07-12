"""
database.py

Thin SQLite data-access layer for EarlyShield AI. Kept dependency-free
(sqlite3 is stdlib) so the project has zero external DB setup - just run
init_db() once and the schema is ready.

Two tables:
    customers   - the bank's customer master records
    predictions - every risk prediction ever run, with the full explainability
                  payload stored as JSON so history can be replayed without
                  re-running the model.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
DB_PATH = os.path.join(DB_DIR, "earlyshield.db")


@contextmanager
def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                income REAL NOT NULL,
                expenses REAL NOT NULL,
                credit_score INTEGER NOT NULL,
                loan_amount REAL NOT NULL,
                loan_type TEXT NOT NULL,
                employment_type TEXT NOT NULL,
                existing_loans INTEGER NOT NULL DEFAULT 0,
                account_balance REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT,
                customer_name TEXT,
                risk_category TEXT NOT NULL,
                risk_probability REAL NOT NULL,
                confidence_score REAL NOT NULL,
                input_payload TEXT NOT NULL,
                contributing_factors TEXT NOT NULL,
                recommended_actions TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Risk Analyst'
            )
        """)


def seed_default_user(password_hash: str):
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("admin",)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                ("admin", password_hash, "Vaishnavi Patil", "Senior Risk Analyst"),
            )


def seed_customers_from_dataframe(df, limit: int = 60):
    """Seed the customers table from the training dataset so the Customer
    Management screen has realistic records on first run."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]
        if count > 0:
            return

        sample = df.sample(n=min(limit, len(df)), random_state=7)
        now = datetime.utcnow().isoformat()
        first_names = ["Aarav", "Vivaan", "Ananya", "Ishaan", "Diya", "Kabir", "Meera",
                       "Rohan", "Saanvi", "Aditya", "Neha", "Karthik", "Priya", "Arjun",
                       "Riya", "Siddharth", "Tanvi", "Yash", "Ira", "Dev"]
        last_names = ["Sharma", "Verma", "Iyer", "Reddy", "Kapoor", "Nair", "Gupta",
                      "Menon", "Chatterjee", "Rao", "Malhotra", "Bose", "Pillai", "Joshi"]

        rng_names = []
        i = 0
        for _, row in sample.iterrows():
            fname = first_names[i % len(first_names)]
            lname = last_names[(i * 3) % len(last_names)]
            full_name = f"{fname} {lname}"
            i += 1
            conn.execute("""
                INSERT INTO customers
                (customer_code, full_name, age, income, expenses, credit_score,
                 loan_amount, loan_type, employment_type, existing_loans,
                 account_balance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["Customer_ID"], full_name, int(row["Age"]), float(row["Income"]),
                float(row["Expenses"]), int(row["Credit_Score"]), float(row["Loan_Amount"]),
                row["Loan_Type"], row["Employment_Type"], int(row["Existing_Loans"]),
                float(row["Account_Balance"]), now, now,
            ))


# ---------------------------------------------------------------------------
# Customer CRUD
# ---------------------------------------------------------------------------

def list_customers(search: str = "", page: int = 1, per_page: int = 10):
    offset = (page - 1) * per_page
    with get_connection() as conn:
        if search:
            like = f"%{search}%"
            rows = conn.execute("""
                SELECT * FROM customers
                WHERE full_name LIKE ? OR customer_code LIKE ? OR loan_type LIKE ?
                ORDER BY id DESC LIMIT ? OFFSET ?
            """, (like, like, like, per_page, offset)).fetchall()
            total = conn.execute("""
                SELECT COUNT(*) AS c FROM customers
                WHERE full_name LIKE ? OR customer_code LIKE ? OR loan_type LIKE ?
            """, (like, like, like)).fetchone()["c"]
        else:
            rows = conn.execute(
                "SELECT * FROM customers ORDER BY id DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]

        return [dict(r) for r in rows], total


def get_customer(customer_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return dict(row) if row else None


def create_customer(data: dict):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO customers
            (customer_code, full_name, age, income, expenses, credit_score,
             loan_amount, loan_type, employment_type, existing_loans,
             account_balance, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["customer_code"], data["full_name"], data["age"], data["income"],
            data["expenses"], data["credit_score"], data["loan_amount"],
            data["loan_type"], data["employment_type"], data["existing_loans"],
            data["account_balance"], now, now,
        ))
        return cursor.lastrowid


def update_customer(customer_id: int, data: dict):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute("""
            UPDATE customers SET
                full_name = ?, age = ?, income = ?, expenses = ?, credit_score = ?,
                loan_amount = ?, loan_type = ?, employment_type = ?, existing_loans = ?,
                account_balance = ?, updated_at = ?
            WHERE id = ?
        """, (
            data["full_name"], data["age"], data["income"], data["expenses"],
            data["credit_score"], data["loan_amount"], data["loan_type"],
            data["employment_type"], data["existing_loans"], data["account_balance"],
            now, customer_id,
        ))


def delete_customer(customer_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

def save_prediction(customer_code, customer_name, risk_category, risk_probability,
                     confidence_score, input_payload, contributing_factors,
                     recommended_actions):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO predictions
            (customer_code, customer_name, risk_category, risk_probability,
             confidence_score, input_payload, contributing_factors,
             recommended_actions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            customer_code, customer_name, risk_category, risk_probability,
            confidence_score, json.dumps(input_payload), json.dumps(contributing_factors),
            json.dumps(recommended_actions), now,
        ))
        return cursor.lastrowid


def list_predictions(search: str = "", page: int = 1, per_page: int = 10):
    offset = (page - 1) * per_page
    with get_connection() as conn:
        if search:
            like = f"%{search}%"
            rows = conn.execute("""
                SELECT * FROM predictions
                WHERE customer_name LIKE ? OR customer_code LIKE ? OR risk_category LIKE ?
                ORDER BY id DESC LIMIT ? OFFSET ?
            """, (like, like, like, per_page, offset)).fetchall()
            total = conn.execute("""
                SELECT COUNT(*) AS c FROM predictions
                WHERE customer_name LIKE ? OR customer_code LIKE ? OR risk_category LIKE ?
            """, (like, like, like)).fetchone()["c"]
        else:
            rows = conn.execute(
                "SELECT * FROM predictions ORDER BY id DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS c FROM predictions").fetchone()["c"]

        results = []
        for r in rows:
            item = dict(r)
            item["input_payload"] = json.loads(item["input_payload"])
            item["contributing_factors"] = json.loads(item["contributing_factors"])
            item["recommended_actions"] = json.loads(item["recommended_actions"])
            results.append(item)
        return results, total


def get_prediction(prediction_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["input_payload"] = json.loads(item["input_payload"])
        item["contributing_factors"] = json.loads(item["contributing_factors"])
        item["recommended_actions"] = json.loads(item["recommended_actions"])
        return item


def delete_prediction(prediction_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM predictions WHERE id = ?", (prediction_id,))


# ---------------------------------------------------------------------------
# Dashboard / analytics aggregates
# ---------------------------------------------------------------------------

def get_dashboard_stats():
    with get_connection() as conn:
        total_customers = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]

        risk_counts = {"Low": 0, "Medium": 0, "High": 0}
        for row in conn.execute("""
            SELECT risk_category, COUNT(*) AS c FROM predictions GROUP BY risk_category
        """).fetchall():
            risk_counts[row["risk_category"]] = row["c"]

        avg_row = conn.execute("SELECT AVG(risk_probability) AS avg_risk FROM predictions").fetchone()
        avg_risk = round((avg_row["avg_risk"] or 0) * 100, 1)

        recent = conn.execute("""
            SELECT * FROM predictions ORDER BY id DESC LIMIT 6
        """).fetchall()
        recent_predictions = []
        for r in recent:
            item = dict(r)
            item["input_payload"] = json.loads(item["input_payload"])
            recent_predictions.append(item)

        total_predictions = conn.execute("SELECT COUNT(*) AS c FROM predictions").fetchone()["c"]

        return {
            "total_customers": total_customers,
            "low_risk": risk_counts["Low"],
            "medium_risk": risk_counts["Medium"],
            "high_risk": risk_counts["High"],
            "average_risk_score": avg_risk,
            "total_predictions": total_predictions,
            "recent_predictions": recent_predictions,
        }


def get_analytics_data():
    with get_connection() as conn:
        risk_counts = {"Low": 0, "Medium": 0, "High": 0}
        for row in conn.execute("""
            SELECT risk_category, COUNT(*) AS c FROM predictions GROUP BY risk_category
        """).fetchall():
            risk_counts[row["risk_category"]] = row["c"]

        monthly = conn.execute("""
            SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS c
            FROM predictions GROUP BY month ORDER BY month
        """).fetchall()
        monthly_predictions = [{"month": r["month"], "count": r["c"]} for r in monthly]

        avg_credit = conn.execute("SELECT AVG(credit_score) AS avg_cs FROM customers").fetchone()["avg_cs"] or 0
        avg_income = conn.execute("SELECT AVG(income) AS avg_inc FROM customers").fetchone()["avg_inc"] or 0

        total_predictions = sum(risk_counts.values())
        high_risk_pct = round((risk_counts["High"] / total_predictions) * 100, 1) if total_predictions else 0.0

        return {
            "risk_distribution": risk_counts,
            "monthly_predictions": monthly_predictions,
            "average_credit_score": round(avg_credit, 0),
            "average_income": round(avg_income, 0),
            "high_risk_percentage": high_risk_pct,
        }
