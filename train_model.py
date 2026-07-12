"""
train_model.py

Trains the EarlyShield pre-delinquency classifier.

Pipeline:
    1. Load the synthetic banking dataset.
    2. Clean + encode categorical fields.
    3. Engineer a couple of derived ratios the raw columns don't expose directly.
    4. Split into train/test.
    5. Fit an XGBoost multi-class classifier (falls back to RandomForest if
       xgboost is unavailable in the runtime environment).
    6. Evaluate and print accuracy / precision / recall / F1 / confusion matrix.
    7. Persist the fitted pipeline + label encoder + feature metadata to
       models/risk_model.pkl so app.py can load it without retraining.

Run:
    python train_model.py
"""

import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

try:
    from xgboost import XGBClassifier
    MODEL_BACKEND = "xgboost"
except ImportError:  # pragma: no cover - fallback for restricted environments
    from sklearn.ensemble import RandomForestClassifier
    MODEL_BACKEND = "random_forest"

DATASET_PATH = os.path.join("dataset", "customer_banking_data.csv")
MODEL_OUTPUT_PATH = os.path.join("models", "risk_model.pkl")
METADATA_OUTPUT_PATH = os.path.join("models", "model_metadata.json")

LOAN_TYPES = ["Personal Loan", "Home Loan", "Auto Loan", "Credit Card", "Education Loan"]
EMPLOYMENT_TYPES = ["Salaried", "Self-Employed", "Business Owner", "Contract/Freelance"]

FEATURE_COLUMNS = [
    "Age",
    "Income",
    "Expenses",
    "Credit_Score",
    "Loan_Amount",
    "Loan_Type_Encoded",
    "Savings",
    "EMI",
    "EMI_Ratio",
    "Salary_Delay_Days",
    "Late_Payments",
    "Credit_Utilization",
    "Employment_Type_Encoded",
    "Transaction_Frequency",
    "Existing_Loans",
    "Account_Balance",
    "Savings_To_Income",
    "Disposable_Income",
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived ratios that give the model a bit more signal than the
    raw columns alone, and encode the two categorical fields."""
    df = df.copy()

    df["Loan_Type_Encoded"] = df["Loan_Type"].apply(
        lambda x: LOAN_TYPES.index(x) if x in LOAN_TYPES else len(LOAN_TYPES)
    )
    df["Employment_Type_Encoded"] = df["Employment_Type"].apply(
        lambda x: EMPLOYMENT_TYPES.index(x) if x in EMPLOYMENT_TYPES else len(EMPLOYMENT_TYPES)
    )

    df["Savings_To_Income"] = (df["Savings"] / df["Income"].replace(0, np.nan)).fillna(0).clip(0, 10)
    df["Disposable_Income"] = df["Income"] - df["Expenses"] - df["EMI"]

    return df


def load_and_prepare_dataset(path: str = DATASET_PATH):
    df = pd.read_csv(path)

    # Basic cleaning: drop any fully-empty rows and clip obviously bad values.
    df = df.dropna(subset=["Income", "Credit_Score", "Risk"])
    df["Credit_Score"] = df["Credit_Score"].clip(300, 900)
    df["EMI_Ratio"] = df["EMI_Ratio"].clip(0, 2)
    df["Credit_Utilization"] = df["Credit_Utilization"].clip(0, 1)

    df = engineer_features(df)

    label_encoder = LabelEncoder()
    df["Risk_Encoded"] = label_encoder.fit_transform(df["Risk"])

    X = df[FEATURE_COLUMNS]
    y = df["Risk_Encoded"]

    return X, y, label_encoder


def build_model():
    if MODEL_BACKEND == "xgboost":
        return XGBClassifier(
            n_estimators=260,
            max_depth=5,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=1.2,
            objective="multi:softprob",
            num_class=3,
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1,
        )
    return RandomForestClassifier(
        n_estimators=400,
        max_depth=12,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )


def main():
    print(f"Model backend: {MODEL_BACKEND}")

    X, y, label_encoder = load_and_prepare_dataset()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = build_model()
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    recall = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1 = f1_score(y_test, y_pred, average="weighted", zero_division=0)
    cm = confusion_matrix(y_test, y_pred)

    print("\n--- Evaluation ---")
    print(f"Accuracy : {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")
    print("Confusion Matrix (rows=actual, cols=predicted):")
    print(cm)
    print("Classes:", list(label_encoder.classes_))

    # Feature importance is used later by the explainability module to
    # rank which fields matter most globally; per-prediction reasons are
    # computed separately in utils/explainability.py using rule-based
    # deviation from healthy thresholds (more transparent for a banking
    # audience than raw SHAP values, and doesn't require the shap package).
    importances = getattr(model, "feature_importances_", None)
    feature_importance = {}
    if importances is not None:
        feature_importance = {
            col: float(imp) for col, imp in zip(FEATURE_COLUMNS, importances)
        }

    os.makedirs("models", exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "label_encoder": label_encoder,
            "feature_columns": FEATURE_COLUMNS,
            "loan_types": LOAN_TYPES,
            "employment_types": EMPLOYMENT_TYPES,
            "backend": MODEL_BACKEND,
        },
        MODEL_OUTPUT_PATH,
    )

    metadata = {
        "backend": MODEL_BACKEND,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "confusion_matrix": cm.tolist(),
        "classes": list(label_encoder.classes_),
        "feature_importance": feature_importance,
        "train_rows": len(X_train),
        "test_rows": len(X_test),
    }
    with open(METADATA_OUTPUT_PATH, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nSaved model -> {MODEL_OUTPUT_PATH}")
    print(f"Saved metadata -> {METADATA_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
