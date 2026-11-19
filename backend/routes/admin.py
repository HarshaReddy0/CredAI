import hmac
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from backend import db
from backend.config import ADMIN_API_KEY, POLICY
from backend.services.decision_engine import build_offers

def require_admin(x_admin_key: Optional[str] = Header(None)):
    if ADMIN_API_KEY and not hmac.compare_digest(x_admin_key or "", ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Admin key required")


router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


class DecisionUpdate(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "MANUAL_REVIEW", "PARTIALLY_APPROVED"]
    note: str = ""


@router.get("/auth")
def auth_check():
    return {"ok": True, "protected": bool(ADMIN_API_KEY)}


@router.get("/stats")
def stats():
    return db.stats()


@router.get("/applications")
def applications(limit: int = 100, decision: Optional[str] = None, q: Optional[str] = None):
    return {"applications": db.list_applications(limit, decision, q)}


@router.get("/applications/{app_id}")
def application(app_id: str):
    rec = db.get_application(app_id)
    if not rec:
        raise HTTPException(404, "Not found")
    rec.pop("pan_hash", None)
    return rec


@router.post("/applications/{app_id}/decision")
def set_decision(app_id: str, body: DecisionUpdate):
    rec = db.get_application(app_id)
    if not rec:
        raise HTTPException(404, "Not found")
    d = rec["decision"]
    if body.decision in ("APPROVED", "PARTIALLY_APPROVED") and not d.get("offers"):
        # underwriter approved a referred case: generate real offers within affordability
        amount = int(min(d["requested_amount"], d["max_eligible_amount"] or d["requested_amount"]))
        max_tenure = int((POLICY["max_age_at_maturity"] - rec["applicant"].get("age_years", 30)) * 12)
        d["approved_amount"] = amount
        d["offers"] = build_offers(amount, d["interest_rate"], d["tenure_months"],
                                   d["affordability"]["max_new_emi"], max(POLICY["min_tenure"], max_tenure))
        db.save_application(rec)
    db.update_status(app_id, body.decision, body.note[:500])
    return {"ok": True}


@router.get("/fraud-alerts")
def fraud_alerts():
    apps = db.list_applications(500)
    return {"alerts": [a for a in apps if a["fraud_level"] in ("MEDIUM", "HIGH")][:100]}
