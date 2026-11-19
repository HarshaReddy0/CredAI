"""LightGBM probability-of-default model.

The model in backend/models was trained on the Home Credit Default Risk data
with class_weight='balanced'. That makes its raw output ~0.5 for an average
applicant, so we apply the standard prior-shift correction to get a real
probability of default (PD). Gender is neutralised (prediction averaged over
both values) so it never changes an applicant's outcome, and per-feature
contributions from LightGBM are grouped into plain-language reason codes.
"""
import json
import math
import os
import pickle
import threading
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

from backend.config import MODELS_DIR, POLICY

_lock = threading.Lock()
_model = None
_encoders: dict[str, dict[str, int]] = {}
_features: list[str] = []

METRO_CITIES = {"mumbai", "delhi", "new delhi", "bengaluru", "bangalore", "chennai", "hyderabad",
                "kolkata", "pune", "ahmedabad", "gurgaon", "gurugram", "noida"}

FACTOR_GROUPS = {
    "Credit history (bureau)": ["EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3", "EXT_SCORE_MEAN"],
    "Loan size vs income": ["AMT_CREDIT", "AMT_GOODS_PRICE", "AMT_ANNUITY", "AMT_INCOME_TOTAL",
                            "CREDIT_TO_INCOME", "ANNUITY_TO_INCOME"],
    "Age": ["DAYS_BIRTH", "AGE_YEARS"],
    "Job stability": ["DAYS_EMPLOYED", "EMPLOYMENT_YEARS", "NAME_INCOME_TYPE"],
    "Education": ["NAME_EDUCATION_TYPE"],
    "Family situation": ["NAME_FAMILY_STATUS", "CNT_CHILDREN"],
    "Assets owned": ["FLAG_OWN_CAR", "FLAG_OWN_REALTY"],
    "Location": ["REGION_RATING_CLIENT", "LIVE_CITY_NOT_WORK_CITY"],
    "Other": ["DAYS_ID_PUBLISH", "HOUR_APPR_PROCESS_START"],
}


def load_models() -> None:
    global _model, _encoders, _features
    if _model is not None:
        return
    with _lock:
        if _model is not None:
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # sklearn version-mismatch notice for LabelEncoder
            with open(os.path.join(MODELS_DIR, "risk_model.pkl"), "rb") as f:
                model = pickle.load(f)
            with open(os.path.join(MODELS_DIR, "label_encoders.pkl"), "rb") as f:
                encs = pickle.load(f)
        with open(os.path.join(MODELS_DIR, "model_features.json")) as f:
            _features = json.load(f)
        # Convert LabelEncoders to plain dicts so prediction doesn't depend on sklearn internals
        _encoders = {col: {str(c): i for i, c in enumerate(le.classes_)} for col, le in encs.items()}
        _model = model


def models_loaded() -> bool:
    return _model is not None


def cibil_to_ext(cibil: float | None) -> float:
    """Map a CIBIL score (300-900) onto the 0-1 bureau-score scale the model was trained on.
    720 (typical Indian borrower) ≈ training median 0.52."""
    if cibil is None:
        return 0.45  # thin file / unknown bureau: slightly conservative vs median
    return float(min(0.9, max(0.02, 0.52 + (float(cibil) - 720) / 350)))


def emi(principal: float, annual_rate: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate / 1200
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def build_features(a: dict, gender_override: str | None = None) -> dict:
    """a = canonical applicant dict produced by the session route."""
    monthly_income = float(a.get("monthly_income") or 0)
    annual_income = max(monthly_income * 12, 1.0)
    loan = float(a.get("loan_amount") or 0)
    tenure = int(a.get("loan_tenure_months") or 24)
    annuity = emi(loan, POLICY["base_rate"] + 4, tenure)  # indicative EMI
    age = float(a.get("age_years") or 30)
    emp_type = a.get("employment_type") or "Working"
    no_job = emp_type in ("Pensioner", "Unemployed", "Student")
    years = float(a.get("work_experience_years") or 0)
    ext = cibil_to_ext(a.get("cibil_score"))
    city = (a.get("city") or "").strip().lower()

    def enc(col: str, val: str) -> int:
        m = _encoders.get(col, {})
        return m.get(val, m.get("XNA", 0))

    model_income_type = {"Farmer": "Working"}.get(emp_type, emp_type)
    f = {
        "AMT_INCOME_TOTAL": annual_income,
        "AMT_CREDIT": loan,
        "AMT_ANNUITY": annuity,
        "AMT_GOODS_PRICE": loan * 0.9,
        "DAYS_BIRTH": -age * 365.25,
        "DAYS_EMPLOYED": 365243 if no_job else -years * 365.25,
        "DAYS_ID_PUBLISH": -3254,  # training median
        "EXT_SOURCE_1": ext,
        "EXT_SOURCE_2": ext,
        "EXT_SOURCE_3": ext,
        "CODE_GENDER": enc("CODE_GENDER", gender_override or a.get("gender") or "XNA"),
        "NAME_EDUCATION_TYPE": enc("NAME_EDUCATION_TYPE", a.get("education") or "Secondary / secondary special"),
        "NAME_INCOME_TYPE": enc("NAME_INCOME_TYPE", model_income_type),
        "NAME_FAMILY_STATUS": enc("NAME_FAMILY_STATUS", a.get("marital_status") or "Single / not married"),
        "FLAG_OWN_CAR": enc("FLAG_OWN_CAR", "Y" if a.get("own_vehicle") == "Y" else "N"),
        "FLAG_OWN_REALTY": enc("FLAG_OWN_REALTY", "Y" if a.get("own_property") == "Y" else "N"),
        "CNT_CHILDREN": min(int(a.get("dependents") or 0), 6),
        "REGION_RATING_CLIENT": 1 if city in METRO_CITIES else 2,
        "HOUR_APPR_PROCESS_START": datetime.now().hour,
        "LIVE_CITY_NOT_WORK_CITY": 0,
        "AGE_YEARS": age,
        "EMPLOYMENT_YEARS": np.nan if no_job else years,
        "CREDIT_TO_INCOME": loan / annual_income,
        "ANNUITY_TO_INCOME": annuity / annual_income,
        "EXT_SCORE_MEAN": ext,
    }
    return {k: f.get(k, 0) for k in _features}


def _prior_shift(p_balanced: float) -> float:
    pi = POLICY["population_default_rate"]
    p = min(max(p_balanced, 1e-6), 1 - 1e-6)
    odds = p / (1 - p) * (pi / (1 - pi))
    return odds / (1 + odds)


def pd_to_score(pd_: float) -> int:
    """Scorecard-style 300-900 score: PD 3% -> 750, every halving of odds = +50 points."""
    odds_good = (1 - pd_) / max(pd_, 1e-6)
    score = 750 + (50 / math.log(2)) * (math.log(odds_good) - math.log(0.97 / 0.03))
    return int(round(min(900, max(300, score))))


def band_for(pd_: float) -> tuple[str, str]:
    if pd_ < 0.04:
        return "LOW", "A"
    if pd_ < 0.08:
        return "MODERATE", "B"
    if pd_ < 0.15:
        return "HIGH", "C"
    return "VERY_HIGH", "D"


def rate_for(pd_: float) -> float:
    return round(min(POLICY["max_rate"], POLICY["base_rate"] + 60 * pd_), 2)


def predict_risk(applicant: dict) -> dict:
    load_models()
    rows = [build_features(applicant, g) for g in ("F", "M")]  # gender-neutral
    df = pd.DataFrame(rows, columns=_features)
    p_bal = _model.predict_proba(df)[:, 1]
    contrib = _model.booster_.predict(df, pred_contrib=True)  # log-odds contributions
    p_bal_mean = float(np.mean(p_bal))
    pd_ = float(np.mean([_prior_shift(p) for p in p_bal]))
    contrib_mean = np.mean(contrib, axis=0)

    groups = []
    for name, cols in FACTOR_GROUPS.items():
        v = float(sum(contrib_mean[_features.index(c)] for c in cols if c in _features))
        groups.append({"factor": name, "impact": round(v, 3),
                       "direction": "increases risk" if v > 0 else "reduces risk"})
    groups.sort(key=lambda g: abs(g["impact"]), reverse=True)

    band, grade = band_for(pd_)
    return {
        "success": True,
        "model": "LightGBM (Home Credit, 25 features) + prior-shift calibration",
        "raw_model_output": round(p_bal_mean, 4),
        "probability_of_default": round(pd_ * 100, 2),
        "risk_score": round(pd_ * 100, 2),  # kept for backwards compatibility
        "credit_score": pd_to_score(pd_),
        "risk_band": band,
        "risk_grade": grade,
        "interest_rate": rate_for(pd_),
        "bureau_data_used": applicant.get("cibil_score") is not None,
        "gender_neutral": True,
        "factors": groups,
    }
