---
title: CredAI
emoji: 🛡️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# CredAI: voice-first video-KYC loan onboarding

Apply for a personal loan by **talking**, in English, Hindi or Kannada. The assistant fills the form for you. A randomised liveness challenge and a face match against your ID photo replace the branch visit. A calibrated LightGBM model, real lending policy rules and a fraud engine then produce an **explainable** decision with three offers you can afford.

Built for **Vibethon 2026, NMIT Bengaluru**.

## Quick start

```bash
# macOS / Linux
./run.sh
# Windows
run_backend.bat
```

Or manually:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Then open **http://127.0.0.1:8000** in **Chrome or Edge**. Camera and microphone only work on `localhost` or `https`.

| Page | URL |
|---|---|
| Landing | `/` |
| Apply (voice + video KYC) | `/apply.html` (add `?lang=hi` or `?lang=kn`) |
| Decision | `/result.html?id=…` |
| Lender dashboard | `/dashboard.html` |
| API docs (Swagger) | `/docs` |

Run the tests: `pip install -r requirements-dev.txt && pytest -q` (21 tests).

## Journey

1. **Start**: choose a language and give three explicit consents (video KYC, bureau, transcript). You can also upload *your bank's own PDF form*; CredAI reads it and only asks for the fields that bank needs.
2. **Identity**: a randomised *blink / turn left / turn right* liveness challenge using 68 facial landmarks, then a 128-d face-descriptor match between your live face and your PAN/Aadhaar photo. All of this runs **in the browser**, and video is never uploaded.
3. **Interview**: "Asha" asks each question aloud. Answers are understood and validated as you speak, including "2.5 lakh", "डेढ़ लाख", "ಎರಡು ಲಕ್ಷ", spoken phone digits ("double nine…"), spelled PAN and dates in any format. You can say *repeat / back / skip*, type instead, or edit the live form directly. The camera keeps watching for face presence and multiple people.
4. **Review & submit**: check everything, then get a decision in about 2 seconds.

## How the decision is made

```
answers ─► KYC validators (PAN structure, Aadhaar Verhoeff, mobile, PIN)
        ─► LightGBM PD model ─► prior-shift calibration ─► 300–900 score + reason codes
        ─► policy rules (age at maturity, min income, employment, CIBIL floor)
        ─► affordability (FOIR ≤ 50%, income multiple) ─► max eligible amount
        ─► fraud engine (liveness, face match, faces, age-vs-face, geo, duplicate PAN/mobile, speed)
        ─► APPROVED / PARTIALLY_APPROVED / MANUAL_REVIEW / REJECTED + 3 offers
```

* **Calibrated, not raw:** the model was trained with `class_weight='balanced'`, so its raw output is inflated. The probabilities are corrected back to the real 8% default base rate.
* **Fair by construction:** every prediction is averaged over both genders, so gender cannot change an outcome.
* **Explainable:** LightGBM's own per-feature contributions are grouped into plain factors ("Credit history", "Loan size vs income", …).
* **Privacy:** only a masked PAN, a salted PAN hash (for duplicate detection) and the last 4 digits of Aadhaar are stored.

## API (main endpoints)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status, model loaded, optional engines |
| GET | `/api/form/schema` | All fields, multilingual questions, options |
| POST | `/api/assistant/next-question` | Next question (handles conditional fields) |
| POST | `/api/assistant/map-answer` | Speech/text → validated value |
| POST | `/api/pdf/parse` | Detect fields in a bank's PDF form |
| POST | `/api/session/start` · `/complete` | Run the full decision and store it |
| GET | `/api/applications/{id}` · `/report.pdf` | Decision + PDF report (with repayment schedule) |
| POST | `/api/risk` | Stateless what-if scoring |
| GET | `/api/emi` | EMI calculator |
| GET/POST | `/api/admin/*` | Stats, applications, fraud alerts, underwriter decision (header `X-Admin-Key`) |
| GET | `/api/tts` | Cloud voice fallback for Hindi/Kannada |
| POST | `/api/face-analyze` · `/face-verify` | Optional server-side face (DeepFace) |

## Configuration

Copy `.env.example` to `.env`. Everything is optional:

* `ADMIN_API_KEY`: protects the lender dashboard. If it's empty, the dashboard runs in open demo mode.
* `GROQ_API_KEY`: an LLM writes the underwriting note and tips. Without it, a deterministic, fact-based note is used.
* `ENABLE_DEEPFACE`: `auto` / `true` / `false`. Install `requirements-face.txt` for server-side DeepFace.

## Deploy

* **Hugging Face Spaces / any Docker host:** `docker build -t credai . && docker run -p 7860:7860 credai`
* **Render:** `render.yaml` is included. Note that the free plan's disk is ephemeral, so set `DATA_DIR` to a persistent disk.

## Project layout

```
backend/
  main.py              app, middleware, static hosting
  config.py            settings + lending policy
  db.py                SQLite persistence
  routes/              assistant, session, applications, admin, face, tools
  services/            form_schema, answer_normalizer, kyc_validators, risk_service,
                       decision_engine, fraud_service, llm_service, report_service,
                       pdf_parser_service, question_engine, face_service
  models/              trained LightGBM + encoders (unchanged)
frontend/
  index.html apply.html result.html dashboard.html
  js/ (common, i18n, face, apply, result, dashboard)   css/app.css
  vendor/face-api/     face-api.js + 4 models served locally (no CDN needed)
tests/test_api.py
```

See **AUDIT.md** for what was broken in v1, what changed, and the roadmap.

## Camera troubleshooting

| Symptom | Fix |
|---|---|
| "Camera only works on 127.0.0.1…" | Open `http://127.0.0.1:8000`, not your LAN IP. Browsers block cameras on plain-http IPs. |
| "Camera is busy in another app" | Close Zoom, Teams, WhatsApp desktop, OBS or other tabs using the camera, then press **Retry**. |
| "Permission is blocked" | Click the 🔒/camera icon in the address bar → Allow → **Retry**. |
| Slow or laggy face check | Enable *Use graphics acceleration* in Chrome/Edge settings → System. Without a GPU, the app shows a warning and runs at a lower frame rate. Good front lighting also helps detection. |
| Blink not detected | Blink slowly and fully, and remove reflective glasses if possible. |
