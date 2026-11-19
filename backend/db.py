"""Tiny SQLite persistence layer (no ORM, thread-safe by opening a
connection per call). Applications survive restarts, PAN de-duplication
works across sessions, and the admin dashboard reads from here."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.config import DB_PATH

_lock = threading.Lock()


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _lock, _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id            TEXT PRIMARY KEY,
                created_at    TEXT NOT NULL,
                name          TEXT,
                phone         TEXT,
                city          TEXT,
                pan_hash      TEXT,
                loan_amount   REAL,
                decision      TEXT,
                risk_score    REAL,
                credit_score  INTEGER,
                risk_band     TEXT,
                fraud_score   INTEGER,
                fraud_level   TEXT,
                status        TEXT,
                reviewer_note TEXT,
                payload       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_app_created ON applications(created_at);
            CREATE TABLE IF NOT EXISTS pan_registry (
                pan_hash   TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                session_id TEXT,
                count      INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                language   TEXT,
                completed  INTEGER DEFAULT 0
            );
            """
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- sessions
def create_session(session_id: str, language: str) -> str:
    started = now_iso()
    with _lock, _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO sessions(id, started_at, language) VALUES (?,?,?)",
            (session_id, started, language),
        )
    return started


def get_session(session_id: str):
    with _conn() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None


def mark_session_complete(session_id: str) -> None:
    with _lock, _conn() as con:
        con.execute("UPDATE sessions SET completed=1 WHERE id=?", (session_id,))


# ---------------------------------------------------------------- PAN registry
def register_pan(pan_hash: str, session_id: str) -> int:
    """Registers a PAN hash and returns how many *previous* applications used it."""
    with _lock, _conn() as con:
        row = con.execute(
            "SELECT count, session_id FROM pan_registry WHERE pan_hash=?", (pan_hash,)
        ).fetchone()
        if row is None:
            con.execute(
                "INSERT INTO pan_registry(pan_hash, first_seen, session_id) VALUES (?,?,?)",
                (pan_hash, now_iso(), session_id),
            )
            return 0
        if row["session_id"] == session_id:  # same session re-submitted
            return 0
        con.execute("UPDATE pan_registry SET count=count+1 WHERE pan_hash=?", (pan_hash,))
        return int(row["count"])


# ---------------------------------------------------------------- applications
def save_application(record: dict) -> None:
    a = record["applicant"]
    with _lock, _conn() as con:
        con.execute(
            """INSERT OR REPLACE INTO applications
               (id, created_at, name, phone, city, pan_hash, loan_amount, decision,
                risk_score, credit_score, risk_band, fraud_score, fraud_level, status,
                reviewer_note, payload)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record["application_id"],
                record["timestamp"],
                a.get("full_name"),
                a.get("phone"),
                a.get("city"),
                record.get("pan_hash"),
                a.get("loan_amount"),
                record["final_decision"],
                record["risk_assessment"]["probability_of_default"],
                record["risk_assessment"]["credit_score"],
                record["risk_assessment"]["risk_band"],
                record["fraud_assessment"]["fraud_score"],
                record["fraud_assessment"]["fraud_level"],
                record.get("status", "OPEN"),
                record.get("reviewer_note"),
                json.dumps(record, default=str),
            ),
        )


def get_application(app_id: str):
    with _conn() as con:
        row = con.execute("SELECT payload, status, reviewer_note FROM applications WHERE id=?",
                          (app_id,)).fetchone()
    if not row:
        return None
    rec = json.loads(row["payload"])
    rec["status"] = row["status"]
    rec["reviewer_note"] = row["reviewer_note"]
    return rec


def list_applications(limit: int = 100, decision: str | None = None, q: str | None = None):
    sql = ("SELECT id, created_at, name, phone, city, loan_amount, decision, risk_score, "
           "credit_score, risk_band, fraud_score, fraud_level, status FROM applications")
    where, args = [], []
    if decision:
        where.append("decision = ?")
        args.append(decision)
    if q:
        where.append("(name LIKE ? OR id LIKE ? OR city LIKE ? OR phone LIKE ?)")
        args += [f"%{q}%"] * 4
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(max(1, min(limit, 1000)))
    with _conn() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def update_status(app_id: str, decision: str, note: str) -> bool:
    with _lock, _conn() as con:
        row = con.execute("SELECT payload FROM applications WHERE id=?", (app_id,)).fetchone()
        if not row:
            return False
        rec = json.loads(row["payload"])
        rec.setdefault("audit_trail", []).append(
            {"t": now_iso(), "event": f"Underwriter set decision to {decision}", "note": note}
        )
        rec["final_decision"] = decision
        con.execute(
            "UPDATE applications SET decision=?, status='REVIEWED', reviewer_note=?, payload=? WHERE id=?",
            (decision, note, json.dumps(rec, default=str), app_id),
        )
        return True


def stats():
    with _conn() as con:
        rows = con.execute(
            "SELECT decision, fraud_level, risk_band, loan_amount, credit_score, created_at "
            "FROM applications"
        ).fetchall()
    rows = [dict(r) for r in rows]
    total = len(rows)
    by_dec, by_band, by_fraud = {}, {}, {}
    for r in rows:
        by_dec[r["decision"]] = by_dec.get(r["decision"], 0) + 1
        by_band[r["risk_band"]] = by_band.get(r["risk_band"], 0) + 1
        by_fraud[r["fraud_level"]] = by_fraud.get(r["fraud_level"], 0) + 1
    approved = by_dec.get("APPROVED", 0) + by_dec.get("PARTIALLY_APPROVED", 0)
    daily = {}
    for r in rows:
        d = (r["created_at"] or "")[:10]
        daily[d] = daily.get(d, 0) + 1
    return {
        "total": total,
        "approved": approved,
        "rejected": by_dec.get("REJECTED", 0),
        "review": by_dec.get("MANUAL_REVIEW", 0),
        "blocked": by_fraud.get("HIGH", 0),
        "approval_rate": round(approved / total * 100, 1) if total else 0,
        "avg_credit_score": round(sum(r["credit_score"] or 0 for r in rows) / total) if total else 0,
        "total_requested": round(sum(r["loan_amount"] or 0 for r in rows)),
        "by_decision": by_dec,
        "by_risk_band": by_band,
        "by_fraud_level": by_fraud,
        "daily": dict(sorted(daily.items())[-14:]),
    }


def other_names_for_phone(phone: str, name: str) -> int:
    if not phone:
        return 0
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT lower(trim(name)) AS n FROM applications WHERE phone=?",
                           (phone,)).fetchall()
    me = (name or "").strip().lower()
    return sum(1 for r in rows if r["n"] and r["n"] != me)
