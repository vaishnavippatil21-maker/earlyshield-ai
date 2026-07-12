"""
generate_dataset.py

Builds a synthetic but realistic retail-banking dataset used to train the
EarlyShield pre-delinquency model. The generator intentionally correlates
risk-driving fields (EMI ratio, utilization, salary delay, late payment
history) with the target label so the resulting classifier has genuine
signal to learn from instead of pure noise.

Run directly to regenerate dataset/customer_banking_data.csv:
    python generate_dataset.py
"""

import numpy as np
import pandas as pd

RNG_SEED = 42
ROW_COUNT = 5200

LOAN_TYPES = ["Personal Loan", "Home Loan", "Auto Loan", "Credit Card", "Education Loan"]
EMPLOYMENT_TYPES = ["Salaried", "Self-Employed", "Business Owner", "Contract/Freelance"]


def _clip(series: pd.Series, low, high) -> pd.Series:
    return series.clip(lower=low, upper=high)


def build_dataset(rows: int = ROW_COUNT, seed: int = RNG_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    age = rng.integers(21, 65, size=rows)

    employment_type = rng.choice(EMPLOYMENT_TYPES, size=rows, p=[0.55, 0.20, 0.15, 0.10])

    # Income varies by employment type - business owners and self-employed
    # show wider spread, salaried customers are more stable.
    base_income = rng.lognormal(mean=10.6, sigma=0.45, size=rows)
    income_multiplier = np.where(
        employment_type == "Business Owner", 1.35,
        np.where(employment_type == "Self-Employed", 1.1,
                 np.where(employment_type == "Contract/Freelance", 0.85, 1.0))
    )
    income = _clip(pd.Series(base_income * income_multiplier), 18000, 450000).round(0)

    expenses_ratio = rng.normal(0.55, 0.14, size=rows)
    expenses_ratio = np.clip(expenses_ratio, 0.25, 0.95)
    expenses = (income * expenses_ratio).round(0)

    credit_score = rng.normal(680, 85, size=rows)
    credit_score = np.clip(credit_score, 300, 900).round(0)

    loan_type = rng.choice(LOAN_TYPES, size=rows, p=[0.30, 0.20, 0.20, 0.20, 0.10])
    loan_amount_base = {
        "Personal Loan": 350000,
        "Home Loan": 3200000,
        "Auto Loan": 850000,
        "Credit Card": 150000,
        "Education Loan": 650000,
    }
    loan_amount = np.array([
        max(20000, rng.normal(loan_amount_base[lt], loan_amount_base[lt] * 0.35))
        for lt in loan_type
    ]).round(0)

    savings = _clip(pd.Series(income * rng.uniform(0.5, 4.5, size=rows)), 0, None).round(0)

    # EMI derived from loan amount with some noise, then ratio computed.
    emi = (loan_amount * rng.uniform(0.018, 0.032, size=rows)).round(0)
    emi_ratio = _clip(pd.Series(emi / income), 0.02, 1.4).round(3)

    # Salary delay days: mostly zero, occasional delays correlated inversely with credit score.
    delay_propensity = _clip(pd.Series((750 - credit_score) / 450), 0, 1)
    salary_delay_days = np.array([
        rng.poisson(lam=max(0.1, p * 9)) for p in delay_propensity
    ])
    salary_delay_days = np.clip(salary_delay_days, 0, 30)

    late_payment_propensity = _clip(pd.Series((720 - credit_score) / 400), 0, 1)
    late_payments = np.array([
        rng.poisson(lam=max(0.05, p * 5)) for p in late_payment_propensity
    ])
    late_payments = np.clip(late_payments, 0, 12)

    utilization = _clip(
        pd.Series(rng.normal(0.4 + delay_propensity * 0.3, 0.18, size=rows)), 0.01, 1.0
    ).round(3)

    transaction_frequency = rng.integers(4, 60, size=rows)

    existing_loans = rng.integers(0, 5, size=rows)

    account_balance = _clip(
        pd.Series(savings * rng.uniform(0.05, 0.6, size=rows)), 500, None
    ).round(0)

    customer_id = [f"CUST{100000 + i}" for i in range(rows)]

    df = pd.DataFrame({
        "Customer_ID": customer_id,
        "Age": age,
        "Income": income.astype(int),
        "Expenses": expenses.astype(int),
        "Credit_Score": credit_score.astype(int),
        "Loan_Amount": loan_amount.astype(int),
        "Loan_Type": loan_type,
        "Savings": savings.astype(int),
        "EMI": emi.astype(int),
        "EMI_Ratio": emi_ratio,
        "Salary_Delay_Days": salary_delay_days.astype(int),
        "Late_Payments": late_payments.astype(int),
        "Credit_Utilization": utilization,
        "Employment_Type": employment_type,
        "Transaction_Frequency": transaction_frequency.astype(int),
        "Existing_Loans": existing_loans.astype(int),
        "Account_Balance": account_balance.astype(int),
    })

    # ---- Composite risk score used only to derive the label ----
    # Higher EMI ratio, utilization, salary delay, late payments, and lower
    # credit score / savings all push risk upward. Weights were tuned by
    # hand so the label distribution looks like a realistic retail book
    # (roughly 60% low, 27% medium, 13% high).
    risk_score = (
        df["EMI_Ratio"] * 2.1
        + df["Credit_Utilization"] * 1.4
        + (df["Salary_Delay_Days"] / 30) * 1.6
        + (df["Late_Payments"] / 12) * 1.9
        + (1 - (df["Credit_Score"] - 300) / 600) * 1.5
        - (df["Savings"] / df["Income"]).clip(0, 5) * 0.35
        + rng.normal(0, 0.35, size=rows)
    )

    low_cut, high_cut = np.quantile(risk_score, [0.60, 0.87])

    def label_from_score(score: float) -> str:
        if score <= low_cut:
            return "Low"
        if score <= high_cut:
            return "Medium"
        return "High"

    df["Risk"] = [label_from_score(s) for s in risk_score]

    return df


if __name__ == "__main__":
    dataset = build_dataset()
    out_path = "customer_banking_data.csv"
    dataset.to_csv(out_path, index=False)
    print(f"Generated {len(dataset)} rows -> {out_path}")
    print(dataset["Risk"].value_counts())
