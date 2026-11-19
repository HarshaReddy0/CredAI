"""Run with:  pytest -q   (from the project root)"""
import os
import random
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ENABLE_DEEPFACE"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from backend.services.answer_normalizer import AnswerNormalizer, parse_amount  # noqa: E402
from backend.services.kyc_validators import validate_aadhaar, validate_pan  # noqa: E402
from backend.services.risk_service import predict_risk  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def answers(**kw):
    a = dict(full_name="Ramya Shetty", dob="1996-03-14", gender="F", marital_status="Single / not married",
             dependents=0, education="Higher education", phone="9845671234", city="Bengaluru", state="Karnataka",
             pincode="560001", employment_type="Working", employer_name="Infosys", work_experience_years=4,
             monthly_income=65000, existing_emi=0, loan_amount=300000, loan_tenure_months=24,
             loan_purpose="education", pan_number="ABCPS%04dK" % random.randint(0, 9999), cibil_score=760,
             own_property="N", own_vehicle="N")
    a.update(kw)
    return a


GOOD_VERIFY = dict(face_match_score=0.8, liveness_passed=True, estimated_age=30, max_faces_seen=1, face_presence_ratio=0.9)


def submit(client, ans, verification=GOOD_VERIFY):
    sid = client.post("/api/session/start", json={}).json()["session_id"]
    return client.post("/api/session/complete", json=dict(
        session_id=sid, answers=ans, verification=verification, consent={"given": True},
        geo={"city": "Bangalore", "state": "Karnataka"}, telemetry={"duration_seconds": 300}))


# ---------------------------------------------------------------- unit
@pytest.mark.parametrize("text,value", [
    ("forty five thousand", 45000), ("2.5 lakh", 250000), ("I want to borrow two lakh", 200000),
    ("डेढ़ लाख", 150000), ("ಎರಡು ಲಕ್ಷ", 200000), ("one lakh fifty thousand", 150000), ("45,000", 45000),
])
def test_amounts(text, value):
    assert parse_amount(text) == value


def test_normalizer_fields():
    n = AnswerNormalizer()
    assert n.normalize("dob", "15th August 1995")["normalized_value"] == "1995-08-15"
    assert n.normalize("gender", "I am a female")["normalized_value"] == "F"
    assert n.normalize("marital_status", "unmarried")["normalized_value"] == "Single / not married"
    assert n.normalize("phone", "nine eight four five double six seven one two three")["normalized_value"] == "9845667123"
    assert n.normalize("own_vehicle", "no I don't have a car")["normalized_value"] == "N"
    assert n.normalize("full_name", "skip")["success"] is False  # required field
    assert n.normalize("cibil_score", "skip")["skipped"] is True  # optional field
    assert n.normalize("dob", "2015-01-01")["success"] is False  # under 18


def test_kyc_validators():
    assert validate_pan("ABCPS1234K")["valid"]
    assert not validate_pan("ABCDE1234F")["valid"]  # 4th char must be a holder type
    assert validate_aadhaar("2341 2341 2346")["valid"]
    assert not validate_aadhaar("234123412341")["valid"]  # Verhoeff checksum


def test_model_responds_to_inputs():
    base = dict(monthly_income=60000, loan_amount=300000, loan_tenure_months=24, age_years=32,
                work_experience_years=5, employment_type="Working")
    good = predict_risk({**base, "cibil_score": 800})["probability_of_default"]
    bad = predict_risk({**base, "cibil_score": 560})["probability_of_default"]
    assert bad > good * 5


def test_gender_neutral():
    base = dict(monthly_income=60000, loan_amount=300000, age_years=32, employment_type="Working")
    assert predict_risk({**base, "gender": "F"}) == predict_risk({**base, "gender": "M"})


# ---------------------------------------------------------------- API
def test_health(client):
    h = client.get("/api/health").json()
    assert h["models_loaded"] is True


def test_happy_path_and_report(client):
    r = submit(client, answers())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["final_decision"] == "APPROVED"
    assert len(j["decision"]["offers"]) == 3
    assert "pan_number" not in j["applicant"]
    pdf = client.get(f"/api/applications/{j['application_id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_affordability_caps_amount(client):
    j = submit(client, answers(monthly_income=30000, loan_amount=2000000, loan_tenure_months=24)).json()
    assert j["final_decision"] in ("PARTIALLY_APPROVED", "REJECTED")
    assert j["decision"]["approved_amount"] <= j["decision"]["max_eligible_amount"]


def test_unemployed_rejected(client):
    j = submit(client, answers(employment_type="Unemployed", monthly_income=20000)).json()
    assert j["final_decision"] == "REJECTED"


def test_no_camera_goes_to_review(client):
    j = submit(client, answers(), verification={}).json()
    assert j["final_decision"] == "MANUAL_REVIEW"


def test_duplicate_pan_flagged(client):
    pan = "ABCPZ9999K"
    submit(client, answers(pan_number=pan, phone="9811111111"))
    submit(client, answers(pan_number=pan, phone="9811111111"))
    j = submit(client, answers(pan_number=pan, phone="9811111111")).json()
    assert any(c["check"] == "PAN not reused" and c["status"] == "fail" for c in j["fraud_assessment"]["checks"])


def test_validation_errors(client):
    r = submit(client, answers(pan_number="BAD", phone="12345"))
    assert r.status_code == 422
    assert len(r.json()["detail"]["errors"]) == 2


def test_assistant_flow(client):
    q = client.post("/api/assistant/next-question", json={"language": "hi", "answers": {}}).json()
    assert q["field_key"] == "full_name" and "नाम" in q["question_text"]
    q = client.post("/api/assistant/next-question", json={"answers": {"employment_type": "Pensioner"},
                                                          "field_keys": ["employment_type", "employer_name"]}).json()
    assert q["completed"]  # employer is not asked to pensioners


def test_admin_override_generates_offers(client):
    j = submit(client, answers(), verification={}).json()
    assert j["final_decision"] == "MANUAL_REVIEW"
    client.post(f"/api/admin/applications/{j['application_id']}/decision", json={"decision": "APPROVED", "note": "ok"})
    g = client.get(f"/api/applications/{j['application_id']}").json()
    assert g["final_decision"] == "APPROVED" and g["decision"]["offers"]
    assert client.get("/api/admin/stats").json()["total"] >= 1


def test_static_and_legacy(client):
    assert client.get("/").status_code == 200
    assert client.get("/apply.html").status_code == 200
    assert client.get("/voice-app.html", follow_redirects=False).headers["location"] == "/apply.html"
