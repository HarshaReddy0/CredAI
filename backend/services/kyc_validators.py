"""Offline KYC format checks used by Indian lenders before calling NSDL /
UIDAI. These catch typos and obviously fake IDs without any external API."""
import hashlib
import re

PAN_RE = re.compile(r"^[A-Z]{3}[ABCFGHLJPT][A-Z][0-9]{4}[A-Z]$")
PAN_HOLDER_TYPES = {
    "P": "Individual", "C": "Company", "H": "HUF", "F": "Firm", "A": "AOP",
    "T": "Trust", "B": "BOI", "L": "Local authority", "J": "Artificial juridical person",
    "G": "Government",
}

# Verhoeff tables (the checksum algorithm UIDAI uses for Aadhaar)
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def validate_pan(pan: str, full_name: str | None = None) -> dict:
    pan = re.sub(r"[^A-Za-z0-9]", "", pan or "").upper()
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
        return {"valid": False, "value": pan,
                "error": "PAN has 10 characters: 5 letters, 4 digits, then 1 letter (e.g. ABCPK1234F)."}
    if not PAN_RE.match(pan):
        return {"valid": False, "value": pan,
                "error": f"The 4th letter of a PAN shows the holder type and can't be '{pan[3]}'. "
                         "For individuals it is 'P'. Please check your PAN card."}
    holder = PAN_HOLDER_TYPES.get(pan[3], "Unknown")
    out = {"valid": True, "value": pan, "holder_type": holder, "warnings": []}
    if pan[3] != "P":
        out["warnings"].append(f"This PAN belongs to a {holder}, not an individual.")
    if full_name:
        # 5th character of an individual PAN is the first letter of the surname
        parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
        if parts and pan[3] == "P" and parts[-1][0].upper() != pan[4]:
            out["warnings"].append(
                "5th letter of PAN usually matches the first letter of the surname — please double-check.")
    return out


def validate_aadhaar(aadhaar: str) -> dict:
    digits = re.sub(r"\D", "", aadhaar or "")
    if len(digits) != 12:
        return {"valid": False, "error": "Aadhaar must have exactly 12 digits."}
    if digits[0] in "01":
        return {"valid": False, "error": "Aadhaar numbers never start with 0 or 1."}
    if not verhoeff_valid(digits):
        return {"valid": False, "error": "Aadhaar checksum failed — a digit is probably wrong."}
    return {"valid": True, "masked": f"XXXX XXXX {digits[-4:]}", "last4": digits[-4:]}


def validate_phone(phone: str) -> dict:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        return {"valid": False, "value": digits,
                "error": "Indian mobile numbers have 10 digits and start with 6, 7, 8 or 9."}
    if len(set(digits)) <= 2:
        return {"valid": False, "value": digits, "error": "That mobile number looks invalid."}
    return {"valid": True, "value": digits}


def validate_pincode(pin: str) -> dict:
    digits = re.sub(r"\D", "", pin or "")
    if not re.fullmatch(r"[1-9]\d{5}", digits):
        return {"valid": False, "value": digits, "error": "PIN code must be 6 digits and not start with 0."}
    return {"valid": True, "value": digits}


def validate_email(email: str) -> dict:
    e = (email or "").strip().lower()
    e = (e.replace(" at the rate ", "@").replace(" at ", "@").replace(" dot ", ".")
          .replace(" underscore ", "_").replace(" ", ""))
    if not re.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", e):
        return {"valid": False, "value": e, "error": "That doesn't look like a valid email address."}
    return {"valid": True, "value": e}


def pan_hash(pan: str) -> str:
    """Store only a salted hash of PAN for duplicate detection (DPDP-friendly)."""
    return hashlib.sha256(("credai::" + pan.upper()).encode()).hexdigest()


def mask_pan(pan: str) -> str:
    return pan[:2] + "XXX" + pan[5:9] + "X" if len(pan) == 10 else "XXXXXXXXXX"
