"""Turns free speech / typed text into clean, validated field values.

Handles English, Hindi and Kannada, Indian number words (lakh, crore),
spoken digits for phone/PIN/PAN, dates said in many ways, and maps
answers onto the canonical option values defined in form_schema."""
import re
from datetime import date

from dateutil import parser as date_parser

from backend.services import kyc_validators as kyc
from backend.services.form_schema import FIELD_MAP

SKIP_WORDS = {"skip", "next", "pass", "don't know", "dont know", "not sure", "no idea",
              "स्किप", "छोड़ो", "छोड़ दो", "पता नहीं", "मालूम नहीं",
              "ಸ್ಕಿಪ್", "ಮುಂದೆ", "ಗೊತ್ತಿಲ್ಲ"}
YES = ["yes", "yeah", "yep", "yup", "sure", "of course", "i do", "i have", "have", "own",
       "हाँ", "हां", "हा", "जी", "जी हाँ", "है", "haan", "ha",
       "ಹೌದು", "ಇದೆ", "ಹೂಂ"]
NO = ["no", "nope", "nah", "don't", "do not", "dont", "not", "none", "never",
      "नहीं", "नही", "ना", "nahi", "nahin",
      "ಇಲ್ಲ", "ಬೇಡ"]

EN_UNITS = {"zero": 0, "nil": 0, "one": 1, "two": 2, "three": 3,
            "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
            "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
            "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
            "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
# words that only mean a digit when someone is reading out a number
SPOKEN_DIGIT_EXTRAS = {"oh": 0, "o": 0, "to": 2, "too": 2, "for": 4, "ate": 8}
HI_UNITS = {"शून्य": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
            "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11,
            "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "सोलह": 16, "सत्रह": 17,
            "अठारह": 18, "उन्नीस": 19, "बीस": 20, "पच्चीस": 25, "तीस": 30, "पैंतीस": 35,
            "चालीस": 40, "पैंतालीस": 45, "पचास": 50, "पचपन": 55, "साठ": 60,
            "सत्तर": 70, "पचहत्तर": 75, "अस्सी": 80, "नब्बे": 90, "डेढ़": 1.5, "ढाई": 2.5,
            "साढ़े": 0}
KN_UNITS = {"ಸೊನ್ನೆ": 0, "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5,
            "ಆರು": 6, "ಏಳು": 7, "ಎಂಟು": 8, "ಒಂಬತ್ತು": 9, "ಹತ್ತು": 10, "ಹನ್ನೆರಡು": 12,
            "ಹದಿನೈದು": 15, "ಇಪ್ಪತ್ತು": 20, "ಇಪ್ಪತ್ತೈದು": 25, "ಮೂವತ್ತು": 30,
            "ನಲವತ್ತು": 40, "ನಲವತ್ತೈದು": 45, "ಐವತ್ತು": 50, "ಅರವತ್ತು": 60, "ಎಪ್ಪತ್ತು": 70,
            "ಎಂಬತ್ತು": 80, "ಎಂಭತ್ತು": 80, "ತೊಂಬತ್ತು": 90, "ತೊಂಭತ್ತು": 90}
SCALES = {"hundred": 100, "sau": 100, "सौ": 100, "ನೂರು": 100,
          "thousand": 1000, "k": 1000, "hazar": 1000, "hazaar": 1000, "हज़ार": 1000,
          "हजार": 1000, "ಸಾವಿರ": 1000,
          "lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000, "laakh": 100000,
          "लाख": 100000, "ಲಕ್ಷ": 100000,
          "crore": 10000000, "crores": 10000000, "cr": 10000000, "करोड़": 10000000,
          "करोड": 10000000, "ಕೋಟಿ": 10000000,
          "million": 1000000}
ALL_UNITS = {**EN_UNITS, **HI_UNITS, **KN_UNITS}

MONTHS = {
    "जनवरी": "january", "फरवरी": "february", "फ़रवरी": "february", "मार्च": "march",
    "अप्रैल": "april", "मई": "may", "जून": "june", "जुलाई": "july", "अगस्त": "august",
    "सितंबर": "september", "सितम्बर": "september", "अक्टूबर": "october",
    "नवंबर": "november", "नवम्बर": "november", "दिसंबर": "december", "दिसम्बर": "december",
    "ಜನವರಿ": "january", "ಫೆಬ್ರವರಿ": "february", "ಮಾರ್ಚ್": "march", "ಏಪ್ರಿಲ್": "april",
    "ಮೇ": "may", "ಜೂನ್": "june", "ಜುಲೈ": "july", "ಆಗಸ್ಟ್": "august",
    "ಸೆಪ್ಟೆಂಬರ್": "september", "ಅಕ್ಟೋಬರ್": "october", "ನವೆಂಬರ್": "november",
    "ಡಿಸೆಂಬರ್": "december",
}

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
KANNADA_DIGITS = str.maketrans("೦೧೨೩೪೫೬೭೮೯", "0123456789")


def _clean(text: str) -> str:
    t = (text or "").strip().translate(DEVANAGARI_DIGITS).translate(KANNADA_DIGITS)
    t = t.replace("₹", " ").replace("rs.", " ").replace("rupees", " ").replace("rupee", " ")
    t = t.replace("रुपये", " ").replace("रुपए", " ").replace("ರೂಪಾಯಿ", " ")
    return re.sub(r"\s+", " ", t).strip()


def _ok(key, raw, value, display, confidence=0.95, warnings=None, extra=None):
    out = {"success": True, "field_key": key, "raw_answer": raw, "normalized_value": value,
           "display_value": display, "confidence": confidence, "needs_confirmation": False,
           "warnings": warnings or []}
    if extra:
        out.update(extra)
    return out


def _retry(key, raw, msg):
    return {"success": False, "field_key": key, "raw_answer": raw, "needs_confirmation": True,
            "error": msg, "confirmation_question": msg}


def parse_amount(text: str):
    """'2.5 lakh' -> 250000, 'forty five thousand' -> 45000, '45,000' -> 45000,
    'डेढ़ लाख' -> 150000, '1 crore 20 lakh' -> 12000000."""
    t = _clean(text).lower().replace(",", "")
    t = re.sub(r"(\d)\s*k\b", r"\1 thousand", t)
    t = t.replace("-", " ").replace(" and ", " ").replace(" a half", " half")
    tokens = re.findall(r"\d+(?:\.\d+)?|[^\s\d]+", t)
    total, current, seen = 0.0, 0.0, False
    half_pending = False
    for tok in tokens:
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            current += float(tok)
            seen = True
        elif tok in ALL_UNITS:
            if tok == "साढ़े":
                half_pending = True
                continue
            current += ALL_UNITS[tok]
            seen = True
        elif tok == "half":
            current += 0.5
            seen = True
        elif tok in SCALES:
            s = SCALES[tok]
            if half_pending:
                current += 0.5
                half_pending = False
            if s == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * s
                current = 0
            seen = True
    total += current
    return total if seen else None


def parse_digit_string(text: str) -> str:
    """'nine eight four five ... ' / 'double nine' / '98 45 6' -> '98456...'"""
    t = _clean(text).lower().replace("-", " ")
    out = []
    tokens = t.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        mult = 1
        if tok in ("double", "triple") and i + 1 < len(tokens):
            mult = 2 if tok == "double" else 3
            i += 1
            tok = tokens[i]
        if tok.isdigit():
            out.append(tok * mult if mult > 1 and len(tok) == 1 else tok)
        else:
            v = ALL_UNITS.get(tok, SPOKEN_DIGIT_EXTRAS.get(tok))
            if isinstance(v, int) and 0 <= v <= 9:
                out.append(str(v) * mult)
            else:
                digits = re.sub(r"\D", "", tok)
                if digits:
                    out.append(digits)
        i += 1
    return "".join(out)


def parse_date(text: str):
    t = _clean(text).lower()
    for k, v in MONTHS.items():
        t = t.replace(k, v)
    t = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", t)
    t = re.sub(r"\b(of|the|on|born|my|date|birth|is|dob)\b", " ", t)
    # "15 8 1995" or "15081995"
    m = re.fullmatch(r"\s*(\d{1,2})\D+(\d{1,2})\D+(\d{4})\s*", t)
    if m:
        t = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    elif re.fullmatch(r"\s*\d{8}\s*", t):
        s = t.strip()
        t = f"{s[:2]}/{s[2:4]}/{s[4:]}"
    try:
        d = date_parser.parse(t, fuzzy=True, dayfirst=True, default=date_parser.parse("2000-01-01")).date()
    except (ValueError, OverflowError):
        return None
    if not re.search(r"\b(19|20)\d{2}\b", t):
        return None  # a year is mandatory
    return d


def age_from_dob(d: date) -> float:
    today = date.today()
    return (today - d).days / 365.25


class AnswerNormalizer:
    def normalize(self, field_key: str, raw_answer: str, language: str = "en",
                  field_type: str | None = None, context: dict | None = None) -> dict:
        raw = (raw_answer or "").strip()
        field = FIELD_MAP.get(field_key, {"key": field_key, "type": field_type or "text", "required": False})
        ftype = field.get("type", field_type or "text")
        low = raw.lower().strip(" .!?।")
        context = context or {}

        if not raw:
            return _retry(field_key, raw, "I didn't catch that. Could you say it again?")

        if low in SKIP_WORDS or any(low == w for w in SKIP_WORDS):
            if field.get("required"):
                return _retry(field_key, raw, f"{field['label']['en']} is required for the loan. Please answer this one.")
            return _ok(field_key, raw, None, "Skipped", 1.0, extra={"skipped": True})

        try:
            if ftype == "select":
                return self._select(field, raw, low)
            if ftype == "boolean":
                return self._boolean(field_key, raw, low)
            if ftype in ("number", "money"):
                return self._number(field, raw)
            if ftype == "date":
                d = parse_date(raw)
                if not d:
                    return _retry(field_key, raw, "Please say your full date of birth, for example 15 August 1995.")
                age = age_from_dob(d)
                if age < 18:
                    return _retry(field_key, raw, f"That gives an age of {int(age)}. You must be at least 18 to apply.")
                if age > 100:
                    return _retry(field_key, raw, "That date looks too old. Please say your date of birth again.")
                return _ok(field_key, raw, d.isoformat(), d.strftime("%d %b %Y"),
                           extra={"age": round(age, 1)})
            if ftype == "phone":
                r = kyc.validate_phone(parse_digit_string(raw))
                if not r["valid"]:
                    return _retry(field_key, raw, r["error"])
                v = r["value"]
                return _ok(field_key, raw, v, f"{v[:5]} {v[5:]}")
            if ftype == "pincode":
                r = kyc.validate_pincode(parse_digit_string(raw))
                return _ok(field_key, raw, r["value"], r["value"]) if r["valid"] else _retry(field_key, raw, r["error"])
            if ftype == "pan":
                spoken = re.sub(r"\b(capital|letter|small)\b", " ", low)
                spoken = " ".join(str(EN_UNITS[w]) if w in EN_UNITS and EN_UNITS[w] <= 9 else w
                                  for w in spoken.split())
                r = kyc.validate_pan(spoken, context.get("full_name"))
                if not r["valid"]:
                    return _retry(field_key, raw, r["error"])
                return _ok(field_key, raw, r["value"], kyc.mask_pan(r["value"]),
                           warnings=r.get("warnings"), extra={"holder_type": r["holder_type"]})
            if ftype == "aadhaar":
                r = kyc.validate_aadhaar(parse_digit_string(raw))
                if not r["valid"]:
                    return _retry(field_key, raw, r["error"])
                return _ok(field_key, raw, r["last4"], r["masked"])
            if ftype == "email":
                r = kyc.validate_email(raw)
                return _ok(field_key, raw, r["value"], r["value"]) if r["valid"] else _retry(field_key, raw, r["error"])

            # free text (names, city, employer)
            text = re.sub(r"^(my name is|i am|i'm|it is|it's|this is|i live in|in)\s+", "", raw,
                          flags=re.I).strip(" .")
            text = re.sub(r"^(मेरा नाम|मैं)\s+", "", text).strip()
            text = re.sub(r"\s+(है|हूँ|हूं)$", "", text).strip()
            if len(text) < 2:
                return _retry(field_key, raw, "Could you please repeat that?")
            if field_key == "full_name":
                if re.search(r"\d", text):
                    return _retry(field_key, raw, "A name shouldn't contain numbers. Please say your full name.")
                text = " ".join(w.capitalize() if w.isascii() else w for w in text.split())
            elif text.isascii():
                text = " ".join(w.capitalize() for w in text.split())
            return _ok(field_key, raw, text, text)
        except Exception as e:  # never 500 on a weird utterance
            return _retry(field_key, raw, f"Sorry, I couldn't understand that ({type(e).__name__}). Please repeat.")

    # ------------------------------------------------------------------ helpers
    def _select(self, field, raw, low):
        best, best_len = None, 0
        for opt in field["options"]:
            candidates = [opt["value"].lower()] + [lbl.lower() for lbl in opt["label"].values()] + opt["syn"]
            for s in candidates:
                s = s.lower()
                if len(s) <= 2:
                    hit = re.search(rf"(?<![a-z]){re.escape(s)}(?![a-z])", low) is not None
                elif s.isascii():
                    hit = re.search(rf"\b{re.escape(s)}\b", low) is not None
                else:
                    hit = s in low
                # prefer the longest synonym ("unmarried" beats "married", "female" beats "male")
                if hit and len(s) > best_len:
                    best, best_len = opt, len(s)
        if not best:
            opts = ", ".join(o["label"]["en"] for o in field["options"])
            return _retry(field["key"], raw, f"Please choose one of: {opts}.")
        return _ok(field["key"], raw, best["value"], best["label"]["en"],
                   extra={"display_i18n": best["label"]})

    def _boolean(self, key, raw, low):
        words = re.findall(r"[\w']+", low)
        has_no = any((w in words) if w.isascii() else (w in low) for w in NO)
        has_yes = any((w in words) if w.isascii() else (w in low) for w in YES)
        if has_no:  # "no I don't have" contains "have" too — negation wins
            return _ok(key, raw, "N", "No")
        if has_yes:
            return _ok(key, raw, "Y", "Yes")
        return _retry(key, raw, "Please answer yes or no.")

    def _number(self, field, raw):
        key = field["key"]
        val = parse_amount(raw)
        if val is None:
            return _retry(key, raw, "I need a number for this. Please say it again.")
        lo, hi = field.get("min"), field.get("max")
        if lo is not None and val < lo:
            return _retry(key, raw, f"That is below the minimum of {format_inr(lo)}. Please say a value of at least {format_inr(lo)}.")
        if hi is not None and val > hi:
            return _retry(key, raw, f"That is above the maximum of {format_inr(hi)}. Please say a smaller value.")
        if field["type"] == "money":
            v = round(val)
            return _ok(key, raw, v, "₹" + format_inr(v))
        v = round(val, 1) if val % 1 else int(val)
        return _ok(key, raw, v, str(v))


def format_inr(n: float) -> str:
    """Indian digit grouping: 1234567 -> 12,34,567"""
    n = int(round(n))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = head + "," + tail
    return ("-" if n < 0 else "") + s
