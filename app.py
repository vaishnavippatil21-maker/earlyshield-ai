"""
app.py

EarlyShield AI - Pre-Delinquency Intervention Engine
Flask application entry point.

Routes are grouped by feature area: auth, dashboard, customers, prediction,
history, analytics, and a couple of export/report endpoints. Business logic
that doesn't belong in a route handler (explainability, recommendations)
lives under utils/.
"""

import csv
import io
import os
from datetime import datetime
from functools import wraps

import joblib
import pandas as pd
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_file, Response
)
from werkzeug.security import check_password_hash, generate_password_hash

import database as db
from utils.explainability import build_contributing_factors
from utils.recommendations import build_recommendations

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "risk_model.pkl")
DATASET_PATH = os.path.join(BASE_DIR, "dataset", "customer_banking_data.csv")

app = Flask(__name__)
app.secret_key = os.environ.get("EARLYSHIELD_SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SESSION_PERMANENT"] = False

# ---------------------------------------------------------------------------
# Startup: load model, initialize DB, seed demo data
# ---------------------------------------------------------------------------

_model_bundle = None


def load_model_bundle():
    global _model_bundle
    if _model_bundle is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                "Model file not found. Run `python train_model.py` first."
            )
        _model_bundle = joblib.load(MODEL_PATH)
    return _model_bundle


def bootstrap_app():
    db.init_db()
    db.seed_default_user(generate_password_hash("earlyshield@123"))
    if os.path.exists(DATASET_PATH):
        df = pd.read_csv(DATASET_PATH)
        db.seed_customers_from_dataframe(df, limit=60)


bootstrap_app()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    return {
        "current_user": {
            "full_name": session.get("full_name"),
            "role": session.get("role"),
            "username": session.get("username"),
        }
    }


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with db.get_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name']}.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    stats = db.get_dashboard_stats()
    return render_template("dashboard.html", stats=stats)


# ---------------------------------------------------------------------------
# Customer management
# ---------------------------------------------------------------------------

LOAN_TYPES = ["Personal Loan", "Home Loan", "Auto Loan", "Credit Card", "Education Loan"]
EMPLOYMENT_TYPES = ["Salaried", "Self-Employed", "Business Owner", "Contract/Freelance"]


@app.route("/customers")
@login_required
def customers():
    search = request.args.get("q", "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 10

    rows, total = db.list_customers(search=search, page=page, per_page=per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        "customers.html",
        customers=rows,
        search=search,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@app.route("/customers/add", methods=["GET", "POST"])
@login_required
def add_customer():
    if request.method == "POST":
        data = _extract_customer_form(request.form)
        try:
            db.create_customer(data)
            flash(f"Customer {data['full_name']} added successfully.", "success")
            return redirect(url_for("customers"))
        except Exception as exc:  # duplicate customer code, etc.
            flash(f"Could not save customer: {exc}", "danger")

    return render_template(
        "customer_form.html",
        customer=None,
        loan_types=LOAN_TYPES,
        employment_types=EMPLOYMENT_TYPES,
    )


@app.route("/customers/edit/<int:customer_id>", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    customer = db.get_customer(customer_id)
    if not customer:
        flash("Customer not found.", "danger")
        return redirect(url_for("customers"))

    if request.method == "POST":
        data = _extract_customer_form(request.form)
        db.update_customer(customer_id, data)
        flash(f"Customer {data['full_name']} updated.", "success")
        return redirect(url_for("customers"))

    return render_template(
        "customer_form.html",
        customer=customer,
        loan_types=LOAN_TYPES,
        employment_types=EMPLOYMENT_TYPES,
    )


@app.route("/customers/delete/<int:customer_id>", methods=["POST"])
@login_required
def delete_customer(customer_id):
    db.delete_customer(customer_id)
    flash("Customer record deleted.", "info")
    return redirect(url_for("customers"))


def _extract_customer_form(form) -> dict:
    return {
        "customer_code": form.get("customer_code", "").strip() or f"CUST{int(datetime.utcnow().timestamp())}",
        "full_name": form.get("full_name", "").strip(),
        "age": int(form.get("age", 0)),
        "income": float(form.get("income", 0)),
        "expenses": float(form.get("expenses", 0)),
        "credit_score": int(form.get("credit_score", 0)),
        "loan_amount": float(form.get("loan_amount", 0)),
        "loan_type": form.get("loan_type", LOAN_TYPES[0]),
        "employment_type": form.get("employment_type", EMPLOYMENT_TYPES[0]),
        "existing_loans": int(form.get("existing_loans", 0)),
        "account_balance": float(form.get("account_balance", 0)),
    }


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

@app.route("/predict")
@login_required
def predict_page():
    return render_template(
        "predict.html",
        loan_types=LOAN_TYPES,
        employment_types=EMPLOYMENT_TYPES,
    )


@app.route("/api/predict", methods=["POST"])
@login_required
def api_predict():
    payload = request.get_json(force=True)

    try:
        record = _parse_prediction_payload(payload)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid input: {exc}"}), 400

    bundle = load_model_bundle()
    model = bundle["model"]
    label_encoder = bundle["label_encoder"]
    feature_columns = bundle["feature_columns"]

    features = _build_feature_row(record, bundle)
    feature_df = pd.DataFrame([features], columns=feature_columns)

    probabilities = model.predict_proba(feature_df)[0]
    predicted_index = probabilities.argmax()
    risk_category = label_encoder.inverse_transform([predicted_index])[0]
    risk_probability = float(probabilities[predicted_index])
    confidence_score = float(probabilities.max() / probabilities.sum())

    factors = build_contributing_factors({
        "emi_ratio": record["emi_ratio"],
        "credit_utilization": record["credit_utilization"],
        "credit_score": record["credit_score"],
        "salary_delay_days": record["salary_delay_days"],
        "late_payments": record["late_payments"],
        "savings_to_income": (record["savings_balance"] / record["monthly_income"])
        if record["monthly_income"] else 0,
    })
    actions = build_recommendations(risk_category, factors)

    prediction_id = db.save_prediction(
        customer_code=record.get("customer_code") or None,
        customer_name=record.get("customer_name") or "Walk-in Customer",
        risk_category=risk_category,
        risk_probability=risk_probability,
        confidence_score=confidence_score,
        input_payload=record,
        contributing_factors=factors,
        recommended_actions=actions,
    )

    return jsonify({
        "prediction_id": prediction_id,
        "risk_category": risk_category,
        "risk_probability": round(risk_probability * 100, 1),
        "confidence_score": round(confidence_score * 100, 1),
        "probabilities": {
            label: round(float(prob) * 100, 1)
            for label, prob in zip(label_encoder.classes_, probabilities)
        },
        "contributing_factors": factors,
        "recommended_actions": actions,
    })


def _parse_prediction_payload(payload: dict) -> dict:
    required_numeric = [
        "age", "monthly_income", "monthly_expenses", "current_emi",
        "credit_score", "previous_late_payments", "credit_card_utilization",
        "savings_balance", "loan_amount", "existing_loans", "salary_delay_days",
        "transaction_frequency", "account_balance",
    ]
    record = {}
    for field in required_numeric:
        value = payload.get(field)
        if value is None or value == "":
            raise ValueError(f"'{field}' is required")
        record[field] = float(value)

    record["employment_type"] = payload.get("employment_type", "Salaried")
    record["loan_type"] = payload.get("loan_type", "Personal Loan")
    record["customer_code"] = payload.get("customer_code", "")
    record["customer_name"] = payload.get("customer_name", "")

    income = record["monthly_income"]
    record["emi_ratio"] = (
        payload.get("emi_to_income_ratio")
        and float(payload["emi_to_income_ratio"])
    ) or (record["current_emi"] / income if income else 0)
    record["credit_utilization"] = record["credit_card_utilization"] / 100 if record["credit_card_utilization"] > 1 else record["credit_card_utilization"]
    record["salary_delay_days"] = record["salary_delay_days"]
    record["late_payments"] = record["previous_late_payments"]

    return record


def _build_feature_row(record: dict, bundle: dict) -> dict:
    loan_types = bundle["loan_types"]
    employment_types = bundle["employment_types"]

    loan_type_encoded = (
        loan_types.index(record["loan_type"]) if record["loan_type"] in loan_types else len(loan_types)
    )
    employment_type_encoded = (
        employment_types.index(record["employment_type"])
        if record["employment_type"] in employment_types else len(employment_types)
    )

    income = record["monthly_income"]
    savings_to_income = min(10, record["savings_balance"] / income) if income else 0
    disposable_income = income - record["monthly_expenses"] - record["current_emi"]

    return {
        "Age": record["age"],
        "Income": income,
        "Expenses": record["monthly_expenses"],
        "Credit_Score": record["credit_score"],
        "Loan_Amount": record["loan_amount"],
        "Loan_Type_Encoded": loan_type_encoded,
        "Savings": record["savings_balance"],
        "EMI": record["current_emi"],
        "EMI_Ratio": min(2.0, record["emi_ratio"]),
        "Salary_Delay_Days": record["salary_delay_days"],
        "Late_Payments": record["late_payments"],
        "Credit_Utilization": min(1.0, record["credit_utilization"]),
        "Employment_Type_Encoded": employment_type_encoded,
        "Transaction_Frequency": record["transaction_frequency"],
        "Existing_Loans": record["existing_loans"],
        "Account_Balance": record["account_balance"],
        "Savings_To_Income": savings_to_income,
        "Disposable_Income": disposable_income,
    }


# ---------------------------------------------------------------------------
# Prediction history
# ---------------------------------------------------------------------------

@app.route("/history")
@login_required
def history():
    search = request.args.get("q", "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 10

    rows, total = db.list_predictions(search=search, page=page, per_page=per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        "history.html",
        predictions=rows,
        search=search,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@app.route("/history/delete/<int:prediction_id>", methods=["POST"])
@login_required
def delete_history_record(prediction_id):
    db.delete_prediction(prediction_id)
    flash("Prediction record deleted.", "info")
    return redirect(url_for("history"))


@app.route("/history/export")
@login_required
def export_history_csv():
    rows, _ = db.list_predictions(search="", page=1, per_page=10000)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "ID", "Customer Code", "Customer Name", "Risk Category",
        "Risk Probability (%)", "Confidence (%)", "Created At",
    ])
    for r in rows:
        writer.writerow([
            r["id"], r["customer_code"], r["customer_name"], r["risk_category"],
            round(r["risk_probability"] * 100, 1), round(r["confidence_score"] * 100, 1),
            r["created_at"],
        ])

    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=prediction_history.csv"},
    )


@app.route("/history/<int:prediction_id>/report")
@login_required
def download_report(prediction_id):
    record = db.get_prediction(prediction_id)
    if not record:
        flash("Prediction record not found.", "danger")
        return redirect(url_for("history"))

    pdf_bytes = _generate_prediction_report_pdf(record)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"EarlyShield_Report_{prediction_id}.pdf",
    )


def _generate_prediction_report_pdf(record: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    navy = colors.HexColor("#0B2447")
    accent = colors.HexColor("#1F6FEB")

    c.setFillColor(navy)
    c.rect(0, height - 30 * mm, width, 30 * mm, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, height - 15 * mm, "EarlyShield AI - Risk Assessment Report")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, height - 22 * mm, "Pre-Delinquency Intervention Engine")

    y = height - 45 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, f"Customer: {record['customer_name']} ({record['customer_code'] or 'N/A'})")
    y -= 8 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Report generated: {record['created_at']}")
    y -= 12 * mm

    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, f"Risk Category: {record['risk_category']}")
    y -= 7 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, y, f"Risk Probability: {record['risk_probability'] * 100:.1f}%")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Confidence Score: {record['confidence_score'] * 100:.1f}%")
    y -= 12 * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Top Contributing Factors")
    y -= 7 * mm
    c.setFont("Helvetica", 10)
    for factor in record["contributing_factors"]:
        c.drawString(22 * mm, y, f"- {factor['label']}")
        y -= 5 * mm
        for line in _wrap_text(factor["detail"], 95):
            c.drawString(26 * mm, y, line)
            y -= 5 * mm
        y -= 2 * mm

    y -= 5 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Recommended Interventions")
    y -= 7 * mm
    c.setFont("Helvetica", 10)
    for action in record["recommended_actions"]:
        c.drawString(22 * mm, y, f"- {action['action']} ({action['priority']})")
        y -= 5 * mm
        for line in _wrap_text(action["reason"], 95):
            c.drawString(26 * mm, y, line)
            y -= 5 * mm
        y -= 2 * mm

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawString(20 * mm, 15 * mm, "Generated by EarlyShield AI - for internal relationship-management use only.")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def _wrap_text(text: str, max_chars: int) -> list:
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}".strip()
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.route("/analytics")
@login_required
def analytics():
    data = db.get_analytics_data()
    return render_template("analytics.html", data=data)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
