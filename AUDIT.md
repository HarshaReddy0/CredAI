# CredAI: audit of v1 and what changed in v2

## 1. What was broken in v1 (verified by running it)

### Critical: the core product did not work
| # | Problem | Effect |
|---|---|---|
| 1 | `session.py` built Home Credit column names (`AMT_INCOME_TOTAL`, …) but `predict_risk()` reads lowercase keys (`income`, `credit_amount`, …). | **Every applicant got the same risk score (22.89).** I tested a ₹80k earner with a ₹2L loan and a ₹8k earner with a ₹20L loan, and both scored 22.89. |
| 2 | The model was trained with `class_weight='balanced'`, but its output was used as a real probability. | An "average" person showed ~45% default risk. The bands and interest rates were meaningless. |
| 3 | Without bureau data the model alone rated an unemployed applicant on ₹15k/month asking for ₹20L as LOW risk. | There were no policy or affordability rules to catch this. |
| 4 | The voice page hard-coded `face_match_score: 0.95`, `liveness_passed: true`, `geo_city: "Bengaluru"`, `session_duration: 120`. | The fraud engine always passed, whatever happened. |
| 5 | `face_service.analyze_face()` called `PIL.Image.open()` on a numpy array. | `/api/face-analyze` **always failed**. |
| 6 | `face.py` contained unreachable code after a `return`. | Dead code and confusion. |
| 7 | The static files were mounted at `/` **before** `/api/tts` was registered. | `/api/tts` returned 404, so Hindi voice never played. |
| 8 | `download.py` used `from risk import latest_result`, which copies an empty dict at import time. | The PDF report always said "No Data". It was also one global for all users. |
| 9 | `api.js` and `app.js` ended with `document.getElementById("downloadBtn").addEventListener(...)`. | **A JavaScript crash on every page** without that button: dashboard, landing and onboarding. |
| 10 | The admin routes required `X-Admin-Key`, but the dashboard never sent it. | The dashboard always got 401 and showed nothing. |
| 11 | `api.js submitApplication()` sent `{applicant_data, pan_number}`, but the backend expected `{answers, metadata}`. | The onboarding flow returned 422 errors. |
| 12 | TTS and download used the hard-coded `http://127.0.0.1:8000` / `localhost:8000`. | Broken on every deployment (HF Spaces uses port 7860). |
| 13 | The Groq model `llama3-8b-8192` has been decommissioned. | The LLM always failed. Without a key, a **fixed fake persona** was shown to everyone. |
| 14 | Applications and PAN registry lived in memory. | Everything was lost on restart, and HF Spaces restarts often. |

### Quality / UX issues
* **Three duplicate flows.** `index.html` ≈ `credai-voice-kyc.html`, `voice-app.html` ≈ `credai-voice-loan.html`, plus `onboarding.html`, and each used different field names.
* **Fake marketing numbers** ("98.7% accuracy", "99.2% face accuracy").
* **Fake data in the UI.** The result page invented a mock timeline and fell back to demo data when nothing was stored.
* **No voice fallback.** Without Chrome speech recognition you could not apply at all. No typing, no editing.
* **Weak number parsing.** "I want to borrow two lakh" became 2. "lakh" alone became 0. DOBs were parsed month-first (US style).
* **No validation** of PAN, Aadhaar, mobile, PIN or age.
* **Fairness gap.** Gender was a model input with no mitigation.
* **Privacy gap.** Raw PAN and Aadhaar would have been stored. The face-api CDN was a single point of failure.
* **Repo hygiene.** `__pycache__` and `uvicorn.log` were committed, `model_features.json` was claimed as 25 features but was never validated, `.env` was referenced but not documented, and DeepFace (~1.5 GB of TensorFlow) was required just to start the server.

## 2. What v2 does

* **One coherent journey:** landing → consent → liveness + ID face match → voice/typed interview → review → explained decision → lender dashboard.
* **A single form schema** drives questions, validation, the PDF parser and the UI in three languages.
* **A real risk engine:** fixed feature mapping, prior-shift calibration, a 300–900 score, optional CIBIL input, gender neutralisation and reason codes from LightGBM `pred_contrib`.
* **A real underwriting policy:** age at maturity, minimum income, employment rules, CIBIL floor, FOIR ≤ 50%, income multiple and partial approval.
* **Real offers:** three tenures, EMI, total interest, processing fee, an interactive customiser that respects FOIR, a Key Fact Statement accept flow and a full amortisation schedule in the PDF.
* **A real fraud engine:** 12 transparent checks, each pass/warn/fail with points. These include duplicate PAN (hashed), shared mobile, multiple faces, face presence, age-vs-face, geo (alias-aware: Bangalore = Bengaluru) and speed.
* **In-browser biometrics:** randomised liveness (blink EAR + head yaw) and 128-d face descriptors. The face-api models are bundled locally.
* **Voice that works:** Indian number words in 3 languages, spoken digits, spelled PAN, Hindi/Kannada month names, repeat/back/skip commands, cloud-voice fallback and always-on typing.
* **Persistence:** SQLite stores applications, sessions and the PAN registry. The dashboard has KPIs, charts, a review queue, fraud alerts, search, CSV export, a detail drawer with transcript and audit trail, and approve/reject (which generates offers when approving a referred case).
* **Optional heavy dependencies:** DeepFace and Groq are optional. The core install is about 250 MB.
* **Tests:** 21 pytest tests covering the parsers, validators, model behaviour, fairness, API flows and the admin override, plus a headless-Chrome end-to-end run.

## 3. Ideas to make it more unique (roadmap)

**High impact, buildable next**
1. **Account Aggregator (Sahamati) consent flow.** Pull 6 months of bank statements with consent and compute *verified* income, bounce count and existing EMIs instead of asking for them. This is the biggest jump in accuracy and realism.
2. **Real bureau and KYC APIs** behind a feature flag: NSDL PAN verify (name match), DigiLocker / Aadhaar offline XML eKYC, CIBIL/Experian soft pull.
3. **Voice-stress and consistency signals.** Ask one question twice in different words (e.g. income monthly vs yearly) and flag contradictions in the transcript.
4. **Document OCR.** Read name and DOB from the PAN photo (Tesseract or PaddleOCR) and cross-check them against the spoken answers. Name fuzzy-match is a strong fraud signal.
5. **WhatsApp continuation.** Send the decision link and repayment reminders over the WhatsApp Business API, and let people resume an unfinished application.
6. **Retrain the model on Indian data,** or at least re-weight it. Add monotonic constraints (more income must never mean more risk) and publish a model card with AUC, calibration curve and fairness metrics.

**Differentiators for judges and users**
7. **"Explain my decision" voice playback:** Asha reads the top three reasons aloud in the user's language.
8. **More languages** through the same schema: Tamil, Telugu, Marathi, Bengali. It's just data.
9. **Accessibility mode:** large text, slower speech, and a fully voice-only path for low-literacy users. This is a genuine financial-inclusion story.
10. **Underwriter co-pilot:** an LLM summary of the transcript plus a "questions to ask on the call" list for manual-review cases.
11. **Counter-offer negotiation:** the what-if simulator already exists, so let users pick a counter-offer that the system re-decides live.
12. **Production hardening:** server-side liveness verification (send 3 signed frames), signed consent receipts (hash + timestamp), rate limiting, Postgres, an audit-log export for RBI V-CIP compliance, and encrypted PII at rest.

## 4. Honest limitations (say these out loud in a demo)
* Face match and liveness run in the browser, so a determined attacker could tamper with the client. Production should re-verify frames on the server (DeepFace hooks are already there).
* The risk model was trained on Home Credit (Eastern Europe), not Indian borrowers. Calibration and policy rules make it sensible, but it should be retrained before real use.
* `/api/tts` relies on an unofficial Google endpoint. Use Azure, Google Cloud TTS or Bhashini for production.
* Geo reverse-geocoding uses public Nominatim (fair-use limits).
