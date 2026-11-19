"""Customer profile + plain-language underwriting summary.

Without a GROQ_API_KEY a deterministic profiler builds the same output from
the actual answers (no fake fixed values). With a key, an LLM writes the
summary; any failure silently falls back to the deterministic version."""
import json
import urllib.error
import urllib.request

from backend.config import GROQ_API_KEY, GROQ_MODEL
from backend.services.answer_normalizer import format_inr

PURPOSE_LABEL = {
    "education": "Education", "medical": "Medical", "home_improvement": "Home improvement",
    "business": "Business", "wedding": "Wedding", "vehicle": "Vehicle", "agriculture": "Agriculture",
    "debt_consolidation": "Debt consolidation", "travel": "Travel", "personal": "Personal",
}
EMPLOYMENT_LABEL = {
    "State servant": "Government employee", "Working": "Salaried (private)",
    "Commercial associate": "Business / self-employed", "Farmer": "Farmer",
    "Pensioner": "Pensioner", "Student": "Student", "Unemployed": "Not working",
}


def _income_band(m: float) -> str:
    if m < 25000:
        return "Entry"
    if m < 60000:
        return "Middle"
    if m < 150000:
        return "Upper-middle"
    return "High"


def rule_based_profile(a: dict, risk: dict, decision: dict) -> dict:
    grade = risk["risk_grade"]
    persona = {"A": "Prime", "B": "Near-prime", "C": "Sub-prime", "D": "High-risk"}[grade]
    if not risk.get("bureau_data_used"):
        persona += " (thin file)"
    name = (a.get("full_name") or "The applicant").split()[0]
    emp = EMPLOYMENT_LABEL.get(a.get("employment_type"), a.get("employment_type") or "—")
    purpose = PURPOSE_LABEL.get(a.get("loan_purpose"), a.get("loan_purpose") or "Personal")
    aff = decision["affordability"]
    top = [f for f in risk["factors"] if f["factor"] != "Other"][:3]
    drivers = ", ".join(f"{f['factor'].lower()} ({f['direction']})" for f in top)
    summary = (
        f"{name} is a {int(a.get('age_years') or 0)}-year-old {emp.lower()} earning "
        f"₹{format_inr(a.get('monthly_income') or 0)}/month, requesting ₹{format_inr(a.get('loan_amount') or 0)} "
        f"for {purpose.lower()} over {a.get('loan_tenure_months')} months. "
        f"Total EMIs would be {aff['foir_after_pct']:.0f}% of income (limit {aff['foir_limit_pct']:.0f}%). "
        f"Model PD is {risk['probability_of_default']:.1f}% (grade {grade}); main drivers: {drivers}."
    )
    tips = []
    if aff["foir_after_pct"] > 40:
        tips.append("Choosing a longer tenure or a smaller amount lowers your EMI burden.")
    if not risk.get("bureau_data_used"):
        tips.append("Sharing your CIBIL score can get you a faster decision and a better rate.")
    if a.get("existing_emi"):
        tips.append("Closing a small existing loan first would raise your eligibility.")
    if risk["probability_of_default"] > 8:
        tips.append("Paying all bills on time for 6 months typically improves your credit score.")
    return {
        "source": "rule-based",
        "customer_persona": persona,
        "income_band": _income_band(float(a.get("monthly_income") or 0)),
        "employment": emp,
        "loan_purpose_category": purpose,
        "summary": summary,
        "improvement_tips": tips,
    }


def build_profile(a: dict, risk: dict, decision: dict) -> dict:
    base = rule_based_profile(a, risk, decision)
    if not GROQ_API_KEY:
        return base
    facts = {k: a.get(k) for k in ("age_years", "employment_type", "work_experience_years", "monthly_income",
                                   "existing_emi", "loan_amount", "loan_tenure_months", "loan_purpose",
                                   "education", "own_property", "dependents", "cibil_score")}
    prompt = (
        "You are a credit analyst at an Indian NBFC. Using ONLY these facts, write a 2-3 sentence neutral "
        "underwriting note and up to 3 short, practical tips for the applicant. Never mention gender. "
        "Reply as JSON: {\"summary\": str, \"improvement_tips\": [str]}.\n"
        f"Applicant: {json.dumps(facts)}\nRisk: PD {risk['probability_of_default']}%, grade {risk['risk_grade']}, "
        f"factors {json.dumps(risk['factors'][:4])}\nDecision: {decision['decision']}; "
        f"affordability {json.dumps(decision['affordability'])}"
    )
    body = json.dumps({
        "model": GROQ_MODEL, "temperature": 0.2, "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json",
                 "User-Agent": "CredAI/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            content = json.loads(r.read())["choices"][0]["message"]["content"]
        llm = json.loads(content)
        if isinstance(llm.get("summary"), str):
            base["summary"] = llm["summary"].strip()
        if isinstance(llm.get("improvement_tips"), list):
            base["improvement_tips"] = [str(t) for t in llm["improvement_tips"][:3]]
        base["source"] = f"llm:{GROQ_MODEL}"
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
        base["llm_error"] = type(e).__name__
    return base
