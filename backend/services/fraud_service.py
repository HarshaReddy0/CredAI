"""Rule-based fraud & identity-assurance engine.

Every rule produces a check with status pass / warn / fail / skipped so the
applicant and the underwriter can see exactly why a score was given."""
import difflib
import re


def _norm_city(c: str) -> str:
    c = (c or "").lower().strip()
    c = re.sub(r"\b(city|district|urban|rural|nagar)\b", "", c)
    aliases = {"bangalore": "bengaluru", "bombay": "mumbai", "madras": "chennai", "calcutta": "kolkata",
               "gurgaon": "gurugram", "mysore": "mysuru", "mangalore": "mangaluru", "belgaum": "belagavi",
               "new delhi": "delhi", "trivandrum": "thiruvananthapuram", "poona": "pune",
               "baroda": "vadodara", "vizag": "visakhapatnam"}
    c = re.sub(r"\s+", " ", c).strip()
    return aliases.get(c, c)


def _similar(a: str, b: str) -> bool:
    a, b = _norm_city(a), _norm_city(b)
    if not a or not b:
        return False
    return a == b or a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def detect_fraud(s: dict) -> dict:
    checks = []
    score = 0

    def add(name, status, points, detail):
        nonlocal score
        score += points if status in ("warn", "fail") else 0
        checks.append({"check": name, "status": status, "points": points if status in ("warn", "fail") else 0,
                       "detail": detail})

    # --- face match (live selfie vs ID photo)
    fm = s.get("face_match_score")
    if fm is None:
        add("Face match with ID photo", "warn", 15, "ID photo was not provided, so the face could not be matched.")
    elif fm >= 0.6:
        add("Face match with ID photo", "pass", 0, f"Live face matches ID photo ({fm*100:.0f}% similarity).")
    elif fm >= 0.45:
        add("Face match with ID photo", "warn", 20, f"Borderline face match ({fm*100:.0f}%).")
    else:
        add("Face match with ID photo", "fail", 45, f"Live face does not match the ID photo ({fm*100:.0f}%).")

    # --- liveness
    live = s.get("liveness_passed")
    if live is None:
        add("Liveness (blink + head turn)", "warn", 20, "Liveness check was not completed (camera unavailable).")
    elif live:
        add("Liveness (blink + head turn)", "pass", 0, "Real person confirmed: blink and head-turn challenge passed.")
    else:
        add("Liveness (blink + head turn)", "fail", 45, "Liveness challenge failed — possible photo or video replay.")

    # --- multiple people / face absent during interview
    multi = int(s.get("max_faces_seen") or 0)
    if multi > 1:
        add("Single person on camera", "warn", 15, f"{multi} faces were seen during the interview (possible coaching).")
    elif multi == 1:
        add("Single person on camera", "pass", 0, "Only the applicant was on camera.")
    presence = s.get("face_presence_ratio")
    if presence is not None:
        if presence < 0.5:
            add("Applicant stayed on camera", "warn", 15, f"Face visible only {presence*100:.0f}% of the interview.")
        else:
            add("Applicant stayed on camera", "pass", 0, f"Face visible {presence*100:.0f}% of the interview.")

    # --- age consistency
    declared, est = s.get("declared_age"), s.get("estimated_age")
    if declared and est:
        gap = abs(float(declared) - float(est))
        if gap > 15:
            add("Age matches face", "fail", 25, f"Declared age {declared:.0f} vs face estimate {est:.0f}.")
        elif gap > 10:
            add("Age matches face", "warn", 10, f"Declared age {declared:.0f} vs face estimate {est:.0f}.")
        else:
            add("Age matches face", "pass", 0, f"Declared age {declared:.0f} is consistent with face estimate {est:.0f}.")
    else:
        add("Age matches face", "skipped", 0, "No face age estimate available.")

    # --- location
    dc, gc = s.get("declared_city"), s.get("geo_city")
    if dc and gc:
        if _similar(dc, gc):
            add("Location matches address", "pass", 0, f"Device location ({gc}) matches declared city.")
        elif s.get("geo_state") and s.get("declared_state") and _similar(s["geo_state"], s["declared_state"]):
            add("Location matches address", "pass", 0, f"Device is in {gc}, same state as declared address.")
        else:
            add("Location matches address", "warn", 10, f"Device location ({gc}) differs from declared city ({dc}).")
    else:
        add("Location matches address", "skipped", 0, "Location permission not given.")

    # --- duplicate identity
    dup = int(s.get("pan_previous_uses") or 0)
    if dup >= 2:
        add("PAN not reused", "fail", 50, f"This PAN was used in {dup} earlier applications.")
    elif dup == 1:
        add("PAN not reused", "warn", 15, "This PAN was used in one earlier application.")
    else:
        add("PAN not reused", "pass", 0, "First application with this PAN.")
    phone_names = int(s.get("phone_other_names") or 0)
    if phone_names:
        add("Mobile not shared", "fail", 30, f"This mobile number was used by {phone_names} other applicant name(s).")
    else:
        add("Mobile not shared", "pass", 0, "Mobile number not linked to other applicants.")
    for w in s.get("pan_warnings") or []:
        add("PAN details consistent", "warn", 5, w)

    # --- behaviour
    dur = s.get("session_duration_seconds")
    dur = int(dur) if dur is not None else None
    if dur is not None and dur < 60:
        add("Natural completion time", "warn", 20, f"Application completed in {dur}s — unusually fast.")
    elif dur is not None:
        add("Natural completion time", "pass", 0, f"Completed in {dur//60}m {dur%60}s.")
    corrections = int(s.get("income_corrections") or 0)
    if corrections >= 3:
        add("Stable answers", "warn", 10, f"Income / loan amount was changed {corrections} times.")

    if not s.get("consent_captured"):
        add("Consent recorded", "fail", 100, "Applicant consent for KYC and bureau check was not recorded.")
    else:
        add("Consent recorded", "pass", 0, "Explicit consent captured with timestamp.")

    score = min(score, 100)
    level = "CLEAN" if score == 0 else "LOW" if score <= 20 else "MEDIUM" if score < 60 else "HIGH"
    return {
        "success": True,
        "fraud_score": score,
        "fraud_level": level,
        "block": score >= 60,
        "checks": checks,
        "alerts": [c for c in checks if c["status"] in ("warn", "fail")],
        "face_match_score": fm,
        "liveness_passed": live,
        "estimated_age": est,
        "geo_city": gc,
    }
