import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend import db
from backend.services import kyc_validators as kyc
from backend.services.decision_engine import evaluate
from backend.services.form_schema import FIELD_MAP, FIELDS, is_applicable
from backend.services.fraud_service import detect_fraud
from backend.services.llm_service import build_profile
from backend.services.risk_service import predict_risk

router = APIRouter(prefix="/api/session", tags=["Session"])


class StartRequest(BaseModel):
    language: str = "en"


class Verification(BaseModel):
    face_match_score: Optional[float] = Field(None, ge=0, le=1)
    liveness_passed: Optional[bool] = None
    estimated_age: Optional[float] = Field(None, ge=0, le=120)
    max_faces_seen: Optional[int] = Field(None, ge=0, le=20)
    face_presence_ratio: Optional[float] = Field(None, ge=0, le=1)


class Geo(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None


class Consent(BaseModel):
    given: bool = False
    timestamp: Optional[str] = None
    version: str = "v1"


class Telemetry(BaseModel):
    duration_seconds: Optional[int] = None
    income_corrections: int = 0
    voice_answers: int = 0
    typed_answers: int = 0


class CompleteRequest(BaseModel):
    session_id: str
    language: str = "en"
    answers: Dict[str, Any]
    verification: Verification = Field(default_factory=Verification)
    geo: Geo = Field(default_factory=Geo)
    consent: Consent = Field(default_factory=Consent)
    telemetry: Telemetry = Field(default_factory=Telemetry)
    transcript: List[Dict[str, Any]] = Field(default_factory=list)


@router.post("/start")
def start(req: StartRequest | None = None):
    sid = "CRD-" + datetime.now(timezone.utc).strftime("%y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
    started = db.create_session(sid, (req.language if req else "en"))
    return {"success": True, "session_id": sid, "started_at": started}


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def build_applicant(ans: dict) -> tuple[dict, list, str]:
    errors = []
    for f in FIELDS:
        if f["required"] and is_applicable(f, ans) and ans.get(f["key"]) in (None, ""):
            errors.append(f"{f['label']['en']} is missing.")
    a = {k: v for k, v in ans.items() if k in FIELD_MAP}
    # strings -> numbers
    for k in ("monthly_income", "existing_emi", "loan_amount", "loan_tenure_months", "work_experience_years",
              "dependents", "cibil_score"):
        if a.get(k) not in (None, ""):
            a[k] = _num(a[k])
        else:
            a[k] = None if k == "cibil_score" else 0
    if a.get("cibil_score") is not None and not 300 <= a["cibil_score"] <= 900:
        errors.append("CIBIL score must be between 300 and 900.")
    try:
        dob = date.fromisoformat(str(a.get("dob")))
        a["age_years"] = round((date.today() - dob).days / 365.25, 1)
        if a["age_years"] < 18:
            errors.append("Applicant must be at least 18.")
    except ValueError:
        errors.append("Date of birth must be YYYY-MM-DD.")
        a["age_years"] = 0
    pan = kyc.validate_pan(str(a.get("pan_number") or ""), a.get("full_name"))
    if not pan["valid"]:
        errors.append(pan["error"])
    phone = kyc.validate_phone(str(a.get("phone") or ""))
    if not phone["valid"]:
        errors.append(phone["error"])
    else:
        a["phone"] = phone["value"]
    a["pan_masked"] = kyc.mask_pan(pan.get("value", ""))
    a["pan_warnings"] = pan.get("warnings", [])
    last4 = str(a.pop("aadhaar_number", "") or "")
    a["aadhaar_masked"] = f"XXXX XXXX {last4[-4:]}" if len(last4) >= 4 else None
    a["loan_tenure_months"] = int(a.get("loan_tenure_months") or 24)
    return a, errors, pan.get("value", "")


@router.post("/complete")
def complete(req: CompleteRequest):
    applicant, errors, pan_clean = build_applicant(req.answers)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Application incomplete", "errors": errors})
    applicant.pop("pan_number", None)  # never persist raw PAN

    sess = db.get_session(req.session_id)
    duration = req.telemetry.duration_seconds
    if sess:
        started = datetime.fromisoformat(sess["started_at"])
        duration = int((datetime.now(timezone.utc) - started).total_seconds())

    p_hash = kyc.pan_hash(pan_clean)
    prev_uses = db.register_pan(p_hash, req.session_id)
    v = req.verification
    fraud = detect_fraud({
        "face_match_score": v.face_match_score,
        "liveness_passed": v.liveness_passed,
        "estimated_age": v.estimated_age,
        "declared_age": applicant["age_years"],
        "max_faces_seen": v.max_faces_seen,
        "face_presence_ratio": v.face_presence_ratio,
        "declared_city": applicant.get("city"),
        "declared_state": applicant.get("state"),
        "geo_city": req.geo.city,
        "geo_state": req.geo.state,
        "pan_previous_uses": prev_uses,
        "phone_other_names": db.other_names_for_phone(applicant.get("phone"), applicant.get("full_name")),
        "pan_warnings": applicant.pop("pan_warnings", []),
        "session_duration_seconds": duration,
        "income_corrections": req.telemetry.income_corrections,
        "consent_captured": req.consent.given,
    })
    risk = predict_risk(applicant)
    decision = evaluate(applicant, risk, fraud)
    profile = build_profile(applicant, risk, decision)

    now = db.now_iso()
    trail = []
    if sess:
        trail.append({"t": sess["started_at"], "event": "Session started"})
    if req.consent.given:
        trail.append({"t": req.consent.timestamp or now, "event": f"Consent recorded ({req.consent.version})"})
    if v.liveness_passed is not None:
        trail.append({"t": now, "event": f"Liveness {'passed' if v.liveness_passed else 'failed'}"})
    if v.face_match_score is not None:
        trail.append({"t": now, "event": f"Face match {v.face_match_score*100:.0f}%"})
    trail += [
        {"t": now, "event": f"{len(req.answers)} answers captured "
                             f"({req.telemetry.voice_answers} by voice, {req.telemetry.typed_answers} typed)"},
        {"t": now, "event": f"Risk model: PD {risk['probability_of_default']}% · score {risk['credit_score']}"},
        {"t": now, "event": f"Fraud engine: {fraud['fraud_score']}/100 ({fraud['fraud_level']})"},
        {"t": now, "event": f"Decision: {decision['decision']}"},
    ]

    record = {
        "success": True,
        "application_id": req.session_id,
        "timestamp": now,
        "language": req.language,
        "final_decision": decision["decision"],
        "applicant": applicant,
        "pan_hash": p_hash,
        "risk_assessment": risk,
        "fraud_assessment": fraud,
        "decision": decision,
        "profile": profile,
        "audit_trail": trail,
        "transcript": req.transcript[-200:],
        "status": "OPEN",
    }
    db.save_application(record)
    db.mark_session_complete(req.session_id)
    out = dict(record)
    out.pop("pan_hash")
    return out
