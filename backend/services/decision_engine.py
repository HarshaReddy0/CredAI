"""Credit decision = hard policy rules + affordability (FOIR) + ML risk + fraud.

This mirrors how Indian NBFCs actually underwrite: the ML model ranks risk,
but eligibility and loan size are capped by transparent policy rules."""
from backend.config import POLICY
from backend.services.risk_service import emi
from backend.services.answer_normalizer import format_inr


def present_value(payment: float, annual_rate: float, months: int) -> float:
    if payment <= 0 or months <= 0:
        return 0.0
    r = annual_rate / 1200
    if r == 0:
        return payment * months
    return payment * ((1 + r) ** months - 1) / (r * (1 + r) ** months)


def evaluate(applicant: dict, risk: dict, fraud: dict) -> dict:
    P = POLICY
    rejects, conditions, positives = [], [], []

    income = float(applicant.get("monthly_income") or 0)
    existing = float(applicant.get("existing_emi") or 0)
    requested = float(applicant.get("loan_amount") or 0)
    tenure = int(applicant.get("loan_tenure_months") or 24)
    age = float(applicant.get("age_years") or 0)
    emp = applicant.get("employment_type")
    years = float(applicant.get("work_experience_years") or 0)
    cibil = applicant.get("cibil_score")
    pd_ = risk["probability_of_default"] / 100
    rate = risk["interest_rate"]

    # ------------------------------------------------------------ hard policy
    if age < P["min_age"]:
        rejects.append(f"Minimum age for this loan is {P['min_age']} years.")
    max_tenure_by_age = int((P["max_age_at_maturity"] - age) * 12)
    if max_tenure_by_age < P["min_tenure"]:
        rejects.append(f"The loan must be repaid before age {P['max_age_at_maturity']}.")
    elif tenure > max_tenure_by_age:
        conditions.append(f"Tenure reduced to {max_tenure_by_age} months so the loan ends before age {P['max_age_at_maturity']}.")
        tenure = max_tenure_by_age
    tenure = max(P["min_tenure"], min(P["max_tenure"], tenure))

    if emp == "Unemployed":
        rejects.append("A regular source of income is required.")
    elif emp == "Student":
        conditions.append("Students need an earning co-applicant (parent/guardian).")
    if income < P["min_monthly_income"]:
        rejects.append(f"Minimum monthly income is ₹{format_inr(P['min_monthly_income'])}.")
    if emp in ("Working", "State servant") and years < 1:
        conditions.append("Less than 1 year in current job — latest 3 salary slips needed.")
    if emp == "Commercial associate" and years < 2:
        conditions.append("Business vintage under 2 years — ITR / GST returns needed.")
    if cibil is not None and cibil < 550:
        rejects.append(f"CIBIL score {int(cibil)} is below the minimum of 550.")
    if cibil is None:
        conditions.append("No CIBIL score given — bureau pull will be done before disbursal.")
    if requested < P["min_loan"]:
        rejects.append(f"Minimum loan amount is ₹{format_inr(P['min_loan'])}.")

    # ------------------------------------------------------------ affordability
    max_total_emi = income * P["max_foir"]
    max_new_emi = max(0.0, max_total_emi - existing)
    foir_now = (existing / income) if income else 1
    requested_emi = emi(requested, rate, tenure)
    foir_after = ((existing + requested_emi) / income) if income else 1
    max_by_foir = present_value(max_new_emi, rate, tenure)
    max_by_multiple = income * (25 if pd_ < 0.04 else 20 if pd_ < 0.08 else 12)
    max_eligible = max(0.0, min(max_by_foir, max_by_multiple, P["max_loan"]))
    max_eligible = int(max_eligible // 1000 * 1000)

    if existing and foir_now >= P["max_foir"]:
        rejects.append(f"Existing EMIs already take {foir_now*100:.0f}% of income (limit {P['max_foir']*100:.0f}%).")
    elif max_eligible < P["min_loan"] and not rejects:
        rejects.append("Income is not enough to support the minimum loan amount.")
    if foir_after <= 0.35:
        positives.append(f"Comfortable affordability — total EMIs would be {foir_after*100:.0f}% of income.")
    if applicant.get("own_property") == "Y":
        positives.append("Owns a house / property.")
    if cibil is not None and cibil >= 750:
        positives.append(f"Strong CIBIL score ({int(cibil)}).")
    if emp == "State servant":
        positives.append("Government employment — high income stability.")

    # ------------------------------------------------------------ decision
    reasons = []
    if fraud.get("block"):
        decision = "REJECTED"
        reasons.append("Identity / fraud checks failed.")
    elif rejects:
        decision = "REJECTED"
        reasons += rejects
    elif pd_ >= 0.20:
        decision = "REJECTED"
        reasons.append(f"Estimated default probability {pd_*100:.1f}% exceeds our 20% limit.")
    elif pd_ >= 0.12 or fraud.get("fraud_level") == "MEDIUM" or emp == "Student":
        decision = "MANUAL_REVIEW"
        reasons.append("Sent to an underwriter for a quick manual check.")
    elif requested <= max_eligible:
        decision = "APPROVED"
        reasons.append("Meets all policy, affordability and risk criteria.")
    else:
        decision = "PARTIALLY_APPROVED"
        reasons.append(f"Approved for ₹{format_inr(max_eligible)} — the requested amount would push EMIs above "
                       f"{P['max_foir']*100:.0f}% of income.")

    approved_amount = 0
    offers = []
    if decision in ("APPROVED", "PARTIALLY_APPROVED"):
        approved_amount = int(min(requested, max_eligible))
        offers = build_offers(approved_amount, rate, tenure, max_new_emi, max_tenure_by_age)

    return {
        "decision": decision,
        "reasons": reasons,
        "conditions": conditions,
        "positives": positives,
        "approved_amount": approved_amount,
        "requested_amount": int(requested),
        "max_eligible_amount": max_eligible,
        "interest_rate": rate,
        "tenure_months": tenure,
        "affordability": {
            "monthly_income": income,
            "existing_emi": existing,
            "max_total_emi": round(max_total_emi),
            "max_new_emi": round(max_new_emi),
            "requested_emi": round(requested_emi),
            "foir_before_pct": round(foir_now * 100, 1),
            "foir_after_pct": round(foir_after * 100, 1),
            "foir_limit_pct": P["max_foir"] * 100,
        },
        "offers": offers,
    }


def build_offers(amount: int, rate: float, tenure: int, max_new_emi: float, max_tenure: int) -> list:
    """Three real options: lower EMI (longer), requested tenure, save interest (shorter)."""
    P = POLICY
    candidates = [
        ("Lowest EMI", min(P["max_tenure"], max_tenure, max(tenure + 12, 36)), rate + 0.5),
        ("Recommended", tenure, rate),
        ("Save on interest", max(P["min_tenure"], tenure - 12), max(P["base_rate"], rate - 0.75)),
    ]
    seen, offers = set(), []
    for name, months, r in candidates:
        months = int(max(P["min_tenure"], min(months, max_tenure)))
        if months in seen:
            continue
        seen.add(months)
        r = round(min(P["max_rate"], r), 2)
        amt = amount
        e = emi(amt, r, months)
        if e > max_new_emi and max_new_emi > 0:  # shorter tenure may be unaffordable
            amt = int(present_value(max_new_emi, r, months) // 1000 * 1000)
            e = emi(amt, r, months)
        if amt < P["min_loan"]:
            continue
        fee = round(amt * P["processing_fee_pct"] / 100)
        offers.append({
            "tier": name,
            "amount": amt,
            "interest_rate": r,
            "tenure_months": months,
            "emi": round(e),
            "total_interest": round(e * months - amt),
            "total_payable": round(e * months),
            "processing_fee": fee,
            "recommended": name == "Recommended",
        })
    return offers
