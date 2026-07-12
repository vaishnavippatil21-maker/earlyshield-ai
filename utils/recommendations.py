"""
recommendations.py

Maps a risk category + the specific contributing factors that drove it
into a prioritized list of intervention actions a relationship manager
can action from the dashboard.
"""

def build_recommendations(risk_category: str, factors: list) -> list:
    factor_labels = {f["label"] for f in factors}
    actions = []

    if risk_category == "High":
        actions.append({
            "action": "Assign Relationship Manager",
            "reason": "High-risk accounts need a named owner for proactive follow-up.",
            "priority": "Immediate",
        })
        if "High EMI-to-Income Ratio" in factor_labels or "Elevated EMI-to-Income Ratio" in factor_labels:
            actions.append({
                "action": "Offer EMI Restructuring",
                "reason": "Lowering the monthly EMI directly reduces the customer's repayment burden.",
                "priority": "Immediate",
            })
        if "Frequent Salary Delays" in factor_labels or "Occasional Salary Delay" in factor_labels:
            actions.append({
                "action": "Offer Payment Holiday",
                "reason": "A short repayment pause bridges the gap while salary timing stabilizes.",
                "priority": "This week",
            })
        actions.append({
            "action": "Schedule Call",
            "reason": "A direct conversation surfaces the root cause before the next due date.",
            "priority": "Immediate",
        })
        if "History of Previous Late Payments" in factor_labels:
            actions.append({
                "action": "Offer Financial Counselling",
                "reason": "Repeated late payments suggest a budgeting conversation would help.",
                "priority": "This week",
            })

    elif risk_category == "Medium":
        actions.append({
            "action": "Send SMS Reminder",
            "reason": "A friendly nudge before the due date often prevents a slip into delinquency.",
            "priority": "This week",
        })
        if "Credit Utilization Above 80%" in factor_labels or "Moderate Credit Utilization" in factor_labels:
            actions.append({
                "action": "Offer Financial Counselling",
                "reason": "Rising utilization is a leading indicator worth addressing early.",
                "priority": "This week",
            })
        actions.append({
            "action": "Schedule Call",
            "reason": "A check-in call confirms whether the customer needs support.",
            "priority": "Next 2 weeks",
        })

    else:  # Low
        actions.append({
            "action": "Continue Standard Monitoring",
            "reason": "No immediate intervention required; keep the account on routine review.",
            "priority": "Routine",
        })
        actions.append({
            "action": "Send SMS Reminder",
            "reason": "Standard due-date reminder as part of normal servicing.",
            "priority": "Routine",
        })

    return actions
