"""
explainability.py

Turns a raw customer record + model prediction into human-readable
"why did the model flag this customer" reasons.

We deliberately use rule-based deviation-from-healthy-threshold logic
rather than a black-box SHAP call. For a banking stakeholder, "credit
utilization is 91%, more than double the healthy ceiling of 40%" is far
more actionable than a raw Shapley value, and it keeps the project free
of the extra shap dependency while still being genuinely driven by the
customer's own numbers (not a canned template).
"""

from dataclasses import dataclass


@dataclass
class Factor:
    label: str
    detail: str
    severity: str  # "high", "medium", "low" - drives the badge color in the UI


# Thresholds informed by common retail-banking underwriting heuristics.
THRESHOLDS = {
    "emi_ratio_high": 0.45,
    "emi_ratio_medium": 0.32,
    "utilization_high": 0.80,
    "utilization_medium": 0.55,
    "credit_score_low": 600,
    "credit_score_medium": 675,
    "salary_delay_high": 10,
    "salary_delay_medium": 3,
    "late_payments_high": 4,
    "late_payments_medium": 1,
    "savings_to_income_low": 0.5,
}


def build_contributing_factors(record: dict) -> list:
    """
    record expects the raw (non-encoded) prediction input fields:
    emi_ratio, credit_utilization, credit_score, salary_delay_days,
    late_payments, savings_to_income
    """
    factors = []

    emi_ratio = record.get("emi_ratio", 0)
    if emi_ratio >= THRESHOLDS["emi_ratio_high"]:
        factors.append(Factor(
            "High EMI-to-Income Ratio",
            f"EMI consumes {emi_ratio * 100:.0f}% of monthly income, well above the "
            f"{THRESHOLDS['emi_ratio_high'] * 100:.0f}% safety ceiling underwriters look for.",
            "high",
        ))
    elif emi_ratio >= THRESHOLDS["emi_ratio_medium"]:
        factors.append(Factor(
            "Elevated EMI-to-Income Ratio",
            f"EMI takes up {emi_ratio * 100:.0f}% of income, above the comfortable "
            f"{THRESHOLDS['emi_ratio_medium'] * 100:.0f}% range.",
            "medium",
        ))

    utilization = record.get("credit_utilization", 0)
    if utilization >= THRESHOLDS["utilization_high"]:
        factors.append(Factor(
            "Credit Utilization Above 80%",
            f"Card utilization sits at {utilization * 100:.0f}%, indicating heavy reliance "
            "on revolving credit.",
            "high",
        ))
    elif utilization >= THRESHOLDS["utilization_medium"]:
        factors.append(Factor(
            "Moderate Credit Utilization",
            f"Card utilization is {utilization * 100:.0f}%, trending toward the risk zone.",
            "medium",
        ))

    credit_score = record.get("credit_score", 750)
    if credit_score < THRESHOLDS["credit_score_low"]:
        factors.append(Factor(
            "Low Credit Score",
            f"Credit score of {credit_score:.0f} falls below the {THRESHOLDS['credit_score_low']} "
            "threshold typically associated with elevated default risk.",
            "high",
        ))
    elif credit_score < THRESHOLDS["credit_score_medium"]:
        factors.append(Factor(
            "Below-Average Credit Score",
            f"Credit score of {credit_score:.0f} is below the {THRESHOLDS['credit_score_medium']} "
            "band considered stable.",
            "medium",
        ))

    salary_delay = record.get("salary_delay_days", 0)
    if salary_delay >= THRESHOLDS["salary_delay_high"]:
        factors.append(Factor(
            "Frequent Salary Delays",
            f"Salary credited {salary_delay:.0f} days late on average, disrupting the "
            "customer's repayment cycle.",
            "high",
        ))
    elif salary_delay >= THRESHOLDS["salary_delay_medium"]:
        factors.append(Factor(
            "Occasional Salary Delay",
            f"Salary has been delayed by {salary_delay:.0f} days recently.",
            "medium",
        ))

    late_payments = record.get("late_payments", 0)
    if late_payments >= THRESHOLDS["late_payments_high"]:
        factors.append(Factor(
            "History of Previous Late Payments",
            f"{late_payments:.0f} late payments recorded in recent history, the strongest "
            "single predictor of future delinquency.",
            "high",
        ))
    elif late_payments >= THRESHOLDS["late_payments_medium"]:
        factors.append(Factor(
            "Minor Late Payment History",
            f"{late_payments:.0f} late payment(s) on record.",
            "medium",
        ))

    savings_to_income = record.get("savings_to_income", 1)
    if savings_to_income < THRESHOLDS["savings_to_income_low"]:
        factors.append(Factor(
            "Thin Savings Buffer",
            f"Savings equal only {savings_to_income:.1f}x monthly income, leaving little "
            "cushion for an income shock.",
            "medium",
        ))

    if not factors:
        factors.append(Factor(
            "Healthy Financial Profile",
            "No individual metric breached the underwriting risk thresholds.",
            "low",
        ))

    # Highest severity first so the UI leads with what matters most.
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    factors.sort(key=lambda f: severity_rank[f.severity])

    return [f.__dict__ for f in factors[:5]]
