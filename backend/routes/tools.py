"""Stateless helper endpoints (also handy for testing the engines directly)."""
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.services.decision_engine import evaluate
from backend.services.fraud_service import detect_fraud
from backend.services.risk_service import emi, predict_risk

router = APIRouter(prefix="/api", tags=["Tools"])


class RiskInput(BaseModel):
    monthly_income: float = Field(..., ge=0)
    loan_amount: float = Field(..., gt=0)
    loan_tenure_months: int = Field(24, ge=6, le=60)
    age_years: float = Field(..., ge=18, le=100)
    work_experience_years: float = 2
    existing_emi: float = 0
    employment_type: str = "Working"
    education: str = "Secondary / secondary special"
    marital_status: str = "Single / not married"
    gender: str = "XNA"
    own_property: str = "N"
    own_vehicle: str = "N"
    dependents: int = 0
    cibil_score: Optional[float] = Field(None, ge=300, le=900)
    city: str = ""


@router.post("/risk")
def risk(data: RiskInput):
    a = data.model_dump()
    r = predict_risk(a)
    d = evaluate(a, r, {"block": False, "fraud_level": "CLEAN"})
    return {"risk": r, "decision": d}


@router.post("/fraud")
def fraud(signals: dict):
    return detect_fraud(signals)


@router.get("/emi")
def emi_calc(amount: float = Query(..., gt=0), rate: float = Query(..., gt=0, le=60),
             months: int = Query(..., ge=1, le=360)):
    e = emi(amount, rate, months)
    return {"emi": round(e, 2), "total_payable": round(e * months, 2), "total_interest": round(e * months - amount, 2)}


@lru_cache(maxsize=256)
def _tts(text: str, lang: str) -> bytes:
    url = ("https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl="
           f"{lang}&q={urllib.parse.quote(text)}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()


@router.get("/tts")
def tts(text: str = Query(..., min_length=1, max_length=200), lang: str = Query("en", pattern="^(en|hi|kn)$")):
    """Cloud voice fallback for browsers that have no Hindi/Kannada voice installed."""
    try:
        return Response(_tts(text, lang), media_type="audio/mpeg",
                        headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        raise HTTPException(503, f"Cloud voice unavailable: {type(e).__name__}")
