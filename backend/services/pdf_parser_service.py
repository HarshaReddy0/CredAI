"""Reads any bank's loan application PDF (fillable AcroForm or flat text) and
works out which of our standard fields that bank asks for, so the voice
assistant only asks those questions."""
import io
import re

from backend.services.form_schema import FIELDS

SYNONYMS = {
    "full_name": ["full name", "applicant name", "name of applicant", "name of the applicant", "customer name", "name"],
    "dob": ["date of birth", "d.o.b", "dob", "birth date"],
    "gender": ["gender", "sex"],
    "marital_status": ["marital status", "married", "marital"],
    "dependents": ["dependents", "dependants", "no. of dependents", "number of dependents"],
    "education": ["education", "qualification", "educational qualification"],
    "phone": ["mobile", "mobile number", "phone", "phone number", "contact number", "mobile no"],
    "email": ["email", "e-mail", "email id", "email address"],
    "city": ["city", "town", "village"],
    "state": ["state"],
    "pincode": ["pin code", "pincode", "pin", "postal code", "zip"],
    "employment_type": ["employment type", "occupation", "profession", "employment status", "nature of employment"],
    "employer_name": ["employer", "employer name", "company name", "name of employer", "business name", "organisation"],
    "work_experience_years": ["work experience", "years of experience", "years in current job", "experience", "years in business"],
    "monthly_income": ["monthly income", "net monthly income", "gross monthly income", "salary", "income"],
    "existing_emi": ["existing emi", "existing loans", "current emi", "other loans", "obligations"],
    "loan_amount": ["loan amount", "amount required", "loan required", "amount of loan", "required loan"],
    "loan_tenure_months": ["tenure", "loan tenure", "repayment period", "term"],
    "loan_purpose": ["purpose", "loan purpose", "purpose of loan", "end use"],
    "pan_number": ["pan", "pan number", "pan no", "permanent account number"],
    "aadhaar_number": ["aadhaar", "aadhar", "uid", "aadhaar number"],
    "cibil_score": ["cibil", "credit score", "bureau score"],
    "own_property": ["own house", "residence type", "property", "owned", "house ownership"],
    "own_vehicle": ["vehicle", "car", "two wheeler"],
}


class PDFParserService:
    def _match(self, text: str, found: dict, source: str):
        t = text.lower()
        for key, syns in SYNONYMS.items():
            for s in syns:
                if re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", t):
                    found.setdefault(key, {"matched": s, "source": source})
                    break

    def parse_pdf(self, data: bytes) -> dict:
        found: dict = {}
        pages, acro = 0, 0
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(data))
            pages = len(reader.pages)
            for name in (reader.get_fields() or {}):
                acro += 1
                self._match(name.replace("_", " "), found, "form field")
        except Exception as e:  # corrupted / encrypted pdf
            return {"success": False, "error": f"Could not read PDF: {e}", "fields": []}
        text_chars = 0
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages[:10]:
                    txt = page.extract_text() or ""
                    text_chars += len(txt)
                    for line in txt.splitlines():
                        self._match(line, found, "printed label")
        except Exception:
            pass
        if text_chars == 0 and acro == 0:
            return {"success": False, "error": "This PDF has no readable text (it may be a scanned image). "
                    "Using the standard form instead.", "fields": [], "pages": pages}
        # Core fields needed for any credit decision are always kept
        core = {"full_name", "dob", "phone", "monthly_income", "loan_amount", "loan_tenure_months",
                "employment_type", "pan_number", "city"}
        keys = [f["key"] for f in FIELDS if f["key"] in found or f["key"] in core]
        return {
            "success": True,
            "pages": pages,
            "acroform_fields": acro,
            "detected": [{"field_key": k, **v} for k, v in found.items()],
            "added_core_fields": sorted(core - set(found)),
            "field_keys": keys,
            "total_fields": len(keys),
        }
