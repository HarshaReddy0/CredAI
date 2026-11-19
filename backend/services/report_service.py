"""Generates a real, per-application PDF: sanction letter / decision report
with offer table, repayment schedule, risk factors and verification checks."""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from backend.config import LENDER_NAME
from backend.services.answer_normalizer import format_inr
from backend.services.llm_service import EMPLOYMENT_LABEL, PURPOSE_LABEL

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
BRAND = colors.HexColor("#0f766e")
LINE = colors.HexColor("#e2e8f0")
DECISION_COLORS = {"APPROVED": "#047857", "PARTIALLY_APPROVED": "#0f766e",
                   "MANUAL_REVIEW": "#b45309", "REJECTED": "#b91c1c"}


def rs(n) -> str:
    # Helvetica has no ₹ glyph, so PDFs use "Rs."
    return "Rs. " + format_inr(float(n or 0))


def amortization(amount: float, rate: float, months: int):
    r = rate / 1200
    e = amount * r * (1 + r) ** months / ((1 + r) ** months - 1) if r else amount / months
    bal, rows = amount, []
    for m in range(1, months + 1):
        interest = bal * r
        principal = e - interest
        bal = max(0.0, bal - principal)
        rows.append((m, e, principal, interest, bal))
    return rows


def build_pdf(rec: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"CredAI decision {rec['application_id']}", author=LENDER_NAME)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, textColor=INK, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=BRAND, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13, textColor=INK)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10, textColor=MUTED)

    a = rec["applicant"]
    d = rec["decision"]
    risk = rec["risk_assessment"]
    fraud = rec["fraud_assessment"]
    dec = rec["final_decision"]
    color = colors.HexColor(DECISION_COLORS.get(dec, "#334155"))

    def grid(rows, widths, header=False, zebra=True):
        t = Table(rows, colWidths=widths, hAlign="LEFT")
        style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.8),
                 ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if header:
            style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.8),
                      ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9"))]
        t.setStyle(TableStyle(style))
        return t

    el = []
    el.append(Paragraph(LENDER_NAME, ParagraphStyle("brand", parent=body, textColor=BRAND, fontName="Helvetica-Bold")))
    el.append(Paragraph("Loan Decision Report", h1))
    el.append(Paragraph(f"Application ID <b>{rec['application_id']}</b> &nbsp;·&nbsp; {rec['timestamp'][:19].replace('T', ' ')} UTC", small))
    el.append(Spacer(1, 8))

    banner = Table([[Paragraph(f"<font color='white'><b>{dec.replace('_', ' ')}</b></font>",
                               ParagraphStyle("d", parent=body, fontSize=14)),
                     Paragraph(f"<font color='white'>{' '.join(d['reasons'])}</font>", body)]],
                   colWidths=[55 * mm, 119 * mm])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    el.append(banner)

    el.append(Paragraph("Applicant", h2))
    el.append(grid([
        ["Name", a.get("full_name") or "—", "Mobile", a.get("phone") or "—"],
        ["Date of birth", a.get("dob") or "—", "Age", f"{a.get('age_years', 0):.0f} years"],
        ["City / State", f"{a.get('city') or '—'}, {a.get('state') or '—'}", "PIN", a.get("pincode") or "—"],
        ["Employment", EMPLOYMENT_LABEL.get(a.get("employment_type"), "—"), "Employer", a.get("employer_name") or "—"],
        ["Monthly income", rs(a.get("monthly_income")), "Existing EMIs", rs(a.get("existing_emi"))],
        ["PAN", a.get("pan_masked") or "—", "Aadhaar", a.get("aadhaar_masked") or "Not provided"],
    ], [30 * mm, 57 * mm, 30 * mm, 57 * mm]))

    el.append(Paragraph("Loan request & assessment", h2))
    el.append(grid([
        ["Requested", rs(d["requested_amount"]), "Purpose", PURPOSE_LABEL.get(a.get("loan_purpose"), "—")],
        ["Max eligible", rs(d["max_eligible_amount"]), "Tenure asked", f"{a.get('loan_tenure_months')} months"],
        ["CredAI score", f"{risk['credit_score']} / 900 (grade {risk['risk_grade']})", "Default probability", f"{risk['probability_of_default']}%"],
        ["EMI burden (FOIR)", f"{d['affordability']['foir_after_pct']}% of income", "Fraud score", f"{fraud['fraud_score']} / 100 ({fraud['fraud_level']})"],
    ], [30 * mm, 57 * mm, 30 * mm, 57 * mm]))

    if d["offers"]:
        el.append(Paragraph("Offers", h2))
        rows = [["Option", "Amount", "Rate p.a.", "Tenure", "EMI", "Total interest", "Processing fee"]]
        for o in d["offers"]:
            rows.append([o["tier"] + (" *" if o["recommended"] else ""), rs(o["amount"]), f"{o['interest_rate']}%",
                         f"{o['tenure_months']} m", rs(o["emi"]), rs(o["total_interest"]), rs(o["processing_fee"])])
        el.append(grid(rows, [30 * mm, 26 * mm, 18 * mm, 16 * mm, 24 * mm, 30 * mm, 30 * mm], header=True))
        el.append(Paragraph("* Recommended. Rates are reducing-balance. Final terms subject to document verification.", small))

    if d["conditions"]:
        el.append(Paragraph("Conditions", h2))
        for c in d["conditions"]:
            el.append(Paragraph("• " + c, body))

    el.append(Paragraph("Why this decision — top risk factors", h2))
    rows = [["Factor", "Effect", "Strength"]]
    for f in risk["factors"][:6]:
        mag = abs(f["impact"])
        rows.append([f["factor"], f["direction"], "Strong" if mag > 0.6 else "Moderate" if mag > 0.2 else "Slight"])
    el.append(grid(rows, [60 * mm, 45 * mm, 69 * mm], header=True))
    el.append(Paragraph("Gender is excluded from the decision (prediction averaged across genders).", small))

    el.append(Paragraph("Identity & fraud checks", h2))
    rows = [["Check", "Result", "Detail"]]
    for c in fraud["checks"]:
        rows.append([c["check"], c["status"].upper(), Paragraph(c["detail"], small)])
    el.append(grid(rows, [52 * mm, 18 * mm, 104 * mm], header=True))

    if rec.get("profile", {}).get("summary"):
        el.append(Paragraph("Underwriter note", h2))
        el.append(Paragraph(rec["profile"]["summary"], body))

    if d["offers"]:
        o = next(x for x in d["offers"] if x["recommended"]) if any(x["recommended"] for x in d["offers"]) else d["offers"][0]
        sched = amortization(o["amount"], o["interest_rate"], o["tenure_months"])
        rows = [["Month", "EMI", "Principal", "Interest", "Balance"]]
        for m, e, p, i, b in sched:
            rows.append([str(m), rs(e), rs(p), rs(i), rs(b)])
        el.append(KeepTogether([Paragraph(f"Repayment schedule — {o['tier']}", h2)]))
        el.append(grid(rows, [20 * mm, 38 * mm, 38 * mm, 38 * mm, 40 * mm], header=True))

    el.append(Spacer(1, 10))
    el.append(Paragraph("This is a system-generated decision from a demonstration platform. It is not a binding "
                        "loan sanction. Personal data is stored masked (PAN/Aadhaar) as per data-minimisation "
                        "principles.", small))
    doc.build(el)
    return buf.getvalue()
