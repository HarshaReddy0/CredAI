/* CredAI application flow: start → identity (liveness + ID match) → voice/typed interview → review → submit */
(function () {
  const { api, esc, toast, qs, qsa, inr } = window.Cred;
  const SPEECH_LANG = { en: "en-IN", hi: "hi-IN", kn: "kn-IN" };
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

  const S = {
    lang: "en",
    sessionId: null,
    schema: null,          // {sections, fields}
    fieldKeys: null,       // subset from bank PDF, or null = all
    answers: {},           // key -> normalized value
    display: {},           // key -> human display
    skipped: [],
    current: null,         // current question payload
    history: [],           // keys in order answered
    transcript: [],
    verification: { face_match_score: null, liveness_passed: null, estimated_age: null, max_faces_seen: null, face_presence_ratio: null },
    geo: {},
    consentAt: null,
    telemetry: { income_corrections: 0, voice_answers: 0, typed_answers: 0 },
    liveDescriptor: null,
    voiceOn: true,
    listening: false,
    speaking: false,
    retries: 0,
    stream: null,
    monitor: null,
    faceReady: false,
    busyAnswer: false,
  };
  window.__credaiState = S; // handy for debugging

  // ------------------------------------------------------------------ steps
  const STEPS = ["start", "identity", "interview", "review"];
  function go(step) {
    STEPS.forEach((s) => qs("#step-" + s).classList.toggle("hidden", s !== step));
    const idx = STEPS.indexOf(step);
    qsa("#stepper .s").forEach((el, i) => {
      el.classList.toggle("active", i === idx);
      el.classList.toggle("done", i < idx);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ------------------------------------------------------------------ start
  function initStart() {
    qsa("#lang-seg button").forEach((b) =>
      b.addEventListener("click", () => {
        S.lang = b.dataset.lang;
        qsa("#lang-seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        applyI18n(S.lang);
        qs("#answer").placeholder = t("placeholder");
      })
    );
    const consentBoxes = ["#c1", "#c2", "#c3"].map((s) => qs(s));
    consentBoxes.forEach((c) => c.addEventListener("change", () => {
      qs("#btn-begin").disabled = !consentBoxes.every((x) => x.checked);
    }));

    const drop = qs("#pdf-drop"), input = qs("#pdf-input");
    ["dragenter", "dragover"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove("drag"); }));
    drop.addEventListener("drop", (ev) => { if (ev.dataTransfer.files[0]) handlePdf(ev.dataTransfer.files[0]); });
    input.addEventListener("change", () => input.files[0] && handlePdf(input.files[0]));

    qs("#btn-begin").addEventListener("click", async () => {
      S.consentAt = new Date().toISOString();
      qs("#btn-begin").disabled = true;
      try {
        const s = await api("/api/session/start", { method: "POST", body: { language: S.lang } });
        S.sessionId = s.session_id;
        qs("#sid-pill").textContent = s.session_id;
      } catch (e) {
        toast(e.message, "bad");
        qs("#btn-begin").disabled = false;
        return;
      }
      go("identity");
      startIdentity();
      requestGeo();
    });

    // device capability pills
    const pills = [];
    pills.push(navigator.mediaDevices?.getUserMedia ? ["Camera", "ok"] : ["No camera API", "bad"]);
    pills.push(SR ? ["Voice input", "ok"] : ["Voice input: type instead", "warn"]);
    pills.push("speechSynthesis" in window ? ["Voice output", "ok"] : ["No voice output", "warn"]);
    pills.push(window.isSecureContext ? ["Secure context", "ok"] : ["Use https or localhost", "bad"]);
    qs("#device-pills").innerHTML = pills.map(([l, c]) => `<span class="pill ${c}"><span class="dot"></span>${l}</span>`).join("");
  }

  async function handlePdf(file) {
    if (!/\.pdf$/i.test(file.name)) return toast("Please choose a PDF file.", "warn");
    qs("#pdf-title").textContent = "Reading " + file.name + "…";
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api("/api/pdf/parse", { method: "POST", body: fd, timeout: 60000 });
      if (!r.success) {
        qs("#pdf-title").textContent = file.name;
        qs("#pdf-sub").textContent = r.error;
        S.fieldKeys = null;
        return;
      }
      S.fieldKeys = r.field_keys;
      qs("#pdf-title").textContent = `✓ ${file.name}`;
      qs("#pdf-sub").textContent = `Found ${r.detected.length} known fields on ${r.pages} page(s). We'll ask ${r.total_fields} questions instead of ${S.schema.fields.length}.`;
      toast("Bank form read successfully", "ok");
    } catch (e) {
      qs("#pdf-title").textContent = file.name;
      qs("#pdf-sub").textContent = e.message;
    }
  }

  function requestGeo() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        const { latitude: lat, longitude: lon } = pos.coords;
        const r = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&zoom=10&accept-language=en`);
        const j = await r.json();
        const a = j.address || {};
        S.geo = { city: a.city || a.town || a.county || a.state_district || a.village || "", state: a.state || "" };
      } catch { /* offline or blocked: geo check is skipped */ }
    }, () => {}, { timeout: 10000, maximumAge: 600000 });
  }

  // ------------------------------------------------------------------ identity
  let liveRun = null;
  async function openCamera() {
    if (!window.isSecureContext) {
      throw Object.assign(new Error("insecure"), { name: "InsecureContext" });
    }
    if (!navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error("nocam"), { name: "NotSupportedError" });
    const attempts = [
      { video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24, max: 30 }, facingMode: "user" }, audio: false },
      { video: { facingMode: "user" }, audio: false },
      { video: true, audio: false },
    ];
    let last;
    for (const c of attempts) {
      try { return await navigator.mediaDevices.getUserMedia(c); }
      catch (e) {
        last = e;
        if (e.name === "NotAllowedError" || e.name === "SecurityError") break; // retrying won't help
      }
    }
    throw last;
  }

  function cameraErrorText(e) {
    switch (e && e.name) {
      case "InsecureContext": return "Camera only works on http://127.0.0.1:8000 or http://localhost:8000 (or https). Open the app with that address.";
      case "NotAllowedError": case "SecurityError": return "Camera permission is blocked. Click the camera icon in the address bar → Allow, then press Retry.";
      case "NotReadableError": case "TrackStartError": return "Your camera is busy in another app or tab (Zoom, Teams, WhatsApp, another browser tab). Close it, then press Retry.";
      case "NotFoundError": case "DevicesNotFoundError": return "No camera was found. Connect a webcam, or continue without the identity check.";
      case "NotSupportedError": return "This browser can't access the camera. Use Chrome or Edge.";
      default: return "Couldn't start the camera (" + ((e && (e.name || e.message)) || "unknown error") + "). Press Retry.";
    }
  }

  function stopCamera() {
    if (S.stream) S.stream.getTracks().forEach((tr) => tr.stop());
    S.stream = null;
  }

  async function startIdentity() {
    const tag = qs("#cam-tag");
    qs("#cam-err").classList.add("hidden"); qs("#say").classList.remove("hidden");
    tag.className = "tag pill"; tag.innerHTML = '<span class="dot pulse"></span>Starting camera…';
    stopCamera();
    try {
      S.stream = await openCamera();
      const v = qs("#video");
      v.srcObject = S.stream;
      await new Promise((r) => { if (v.readyState >= 2) r(); else v.onloadeddata = () => r(); setTimeout(r, 4000); });
      await v.play().catch(() => {});
      tag.className = "tag pill ok"; tag.innerHTML = '<span class="dot"></span>Camera on';
      S.stream.getVideoTracks()[0].addEventListener("ended", () => camFail("The camera was disconnected. Press Retry."));
    } catch (e) {
      camFail(cameraErrorText(e));
      return;
    }
    try {
      const off = FaceKit.onStatus((st, msg) => { if (st === "loading") qs("#say-main").textContent = msg; });
      qs("#say-main").textContent = FaceKit.status === "ready" ? "" : t("say_wait");
      await FaceKit.load();
      off();
      S.faceReady = true;
      if (FaceKit.backend !== "webgl") toast("Your device has no graphics acceleration, so face checks run slower — hold still for a moment at each step.", "warn");
    } catch (e) {
      camFail("Face engine could not start (" + e.message + "). You can continue without the identity check.");
      return;
    }
    runLiveness();
  }

  function camFail(msg) {
    const tag = qs("#cam-tag");
    tag.className = "tag pill bad"; tag.innerHTML = '<span class="dot"></span>Unavailable';
    qs("#cam-err").textContent = msg;
    qs("#cam-err").classList.remove("hidden");
    qs("#say").classList.add("hidden");
    qs("#live-status").textContent = msg;
    qs("#btn-live-retry").hidden = false;
  }

  function drawBoxes(res) {
    const v = qs("#video"), c = qs("#overlay");
    if (!v.videoWidth) return;
    if (c.width !== v.videoWidth || c.height !== v.videoHeight) { c.width = v.videoWidth; c.height = v.videoHeight; }
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    qs("#oval").classList.toggle("good", res.length === 1);
    res.forEach((r) => {
      const b = r.detection.box;
      ctx.strokeStyle = res.length === 1 ? "#34d399" : "#f87171";
      ctx.lineWidth = 3;
      ctx.strokeRect(b.x, b.y, b.width, b.height);
    });
  }

  function runLiveness() {
    qs("#btn-live-retry").hidden = true;
    qs("#si-live").classList.remove("ok");
    const chips = qs("#chips");
    liveRun = FaceKit.liveness(qs("#video"), {
      onStep: (step, st) => {
        qs("#say-main").textContent = t(step);
        qs("#say-sub").textContent = `Step ${st.index + 1} of ${st.total}`;
        chips.innerHTML = Array.from({ length: st.total }, (_, i) => `<span class="${i < st.index ? "done" : ""}"></span>`).join("");
      },
      onFrame: (res) => {
        drawBoxes(res);
        if (res.length === 0) qs("#say-sub").textContent = t("center");
        else if (res.length > 1) qs("#say-sub").textContent = "Only one person should be in view";
      },
    });
    liveRun.promise.then((r) => {
      if (r.reason === "cancelled") return; // user chose to skip: "not attempted", not "failed"
      S.verification.liveness_passed = !!r.passed;
      if (r.passed) {
        qs("#say-main").textContent = t("live_ok");
        qs("#say-sub").textContent = "";
        qs("#chips").innerHTML = r.order.map(() => '<span class="done"></span>').join("");
        qs("#si-live").classList.add("ok");
        qs("#live-status").textContent = "Passed — blink and head-turn verified.";
        snapLive();
        qs("#btn-id-next").disabled = false;
        qs("#overlay").getContext("2d").clearRect(0, 0, 9999, 9999);
        // capture the face template once (heavy model) — not during the challenge
        qs("#id-status").textContent = "Capturing your face template… look at the camera.";
        S.descriptorPromise = FaceKit.liveDescriptor(qs("#video")).then((d) => {
          S.liveDescriptor = d;
          qs("#id-status").textContent = d ? "Now upload a clear photo of your PAN or Aadhaar card." : "Couldn't capture your face clearly — look straight at the camera and upload your ID.";
          return d;
        });
      } else if (r.reason !== "cancelled") {
        qs("#say-main").textContent = t("live_fail");
        qs("#live-status").textContent = r.reason === "timeout" ? "Timed out. Make sure your face is well lit and centred." : "Not completed.";
        qs("#btn-live-retry").hidden = false;
      }
    });
  }

  function snapLive() {
    const v = qs("#video"), c = qs("#live-snap");
    c.width = v.videoWidth; c.height = v.videoHeight;
    const ctx = c.getContext("2d");
    ctx.translate(c.width, 0); ctx.scale(-1, 1);
    ctx.drawImage(v, 0, 0);
  }

  async function matchId(imgEl) {
    const box = qs("#match-box");
    box.classList.remove("hidden");
    box.innerHTML = '<span class="pill info"><span class="dot pulse"></span>Finding the face on your ID…</span>';
    if (!S.faceReady) { box.innerHTML = '<span class="pill warn">Face engine not ready</span>'; return; }
    if (!S.liveDescriptor && S.descriptorPromise) await S.descriptorPromise;
    if (!S.liveDescriptor && S.stream) S.liveDescriptor = await FaceKit.liveDescriptor(qs("#video"));
    const idf = await FaceKit.idDescriptor(imgEl);
    if (!idf) {
      box.innerHTML = '<span class="pill warn"><span class="dot"></span>No face found on the ID photo</span><p class="small muted" style="margin-top:6px">Retake it closer, flat, without glare.</p>';
      return;
    }
    if (!S.liveDescriptor) {
      box.innerHTML = '<span class="pill warn"><span class="dot"></span>Look at the camera so we can capture your face</span>';
      return;
    }
    const m = FaceKit.matchScore(S.liveDescriptor, idf.descriptor);
    S.verification.face_match_score = m.score;
    const pct = Math.round(m.score * 100);
    const cls = m.score >= 0.6 ? "ok" : m.score >= 0.45 ? "warn" : "bad";
    const label = m.score >= 0.6 ? "Face matches your ID" : m.score >= 0.45 ? "Partial match — an underwriter will confirm" : "Face does not match the ID";
    box.innerHTML = `<div class="row between"><span class="pill ${cls}"><span class="dot"></span>${label}</span><b>${pct}%</b></div>
      <div class="bar" style="margin-top:8px"><i style="width:${pct}%;background:var(--${cls})"></i></div>
      <p class="small muted" style="margin:6px 0 0">Face distance ${m.distance} (same person is usually below 0.5).</p>`;
    qs("#si-id").classList.toggle("ok", m.score >= 0.45);
    qs("#id-status").textContent = `${pct}% similarity`;
  }

  function initIdentity() {
    qs("#btn-live-retry").addEventListener("click", () => {
      qs("#cam-err").classList.add("hidden"); qs("#say").classList.remove("hidden");
      if (liveRun) liveRun.cancel();
      if (!S.stream || !S.stream.active || !S.faceReady) startIdentity(); else runLiveness();
    });
    qs("#id-file").addEventListener("change", (e) => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 12 * 1024 * 1024) return toast("Image is too large (max 12 MB)", "warn");
      const img = qs("#id-img");
      img.onload = () => matchId(img);
      img.src = URL.createObjectURL(f);
    });
    qs("#btn-id-cam").addEventListener("click", () => {
      if (!S.stream) return toast("Camera is not available", "warn");
      toast("Hold the card steady in front of the camera… capturing in 3 seconds");
      setTimeout(() => {
        const v = qs("#video"), c = document.createElement("canvas");
        c.width = v.videoWidth; c.height = v.videoHeight;
        c.getContext("2d").drawImage(v, 0, 0);
        const img = qs("#id-img");
        img.onload = () => matchId(img);
        img.src = c.toDataURL("image/jpeg", 0.92);
      }, 3000);
    });
    qs("#btn-id-next").addEventListener("click", () => {
      if (S.verification.face_match_score === null && !confirm("You haven't matched your ID photo. Continue anyway? (Your application will need a manual check.)")) return;
      startInterview();
    });
    qs("#btn-id-skip").addEventListener("click", () => {
      if (liveRun) liveRun.cancel();
      startInterview();
    });
  }

  // ------------------------------------------------------------------ interview
  function fieldsInPlay() {
    const keys = S.fieldKeys || S.schema.fields.map((f) => f.key);
    return S.schema.fields.filter((f) => keys.includes(f.key) && applicable(f));
  }
  function applicable(f) {
    if (!f.depends_on) return true;
    return Object.entries(f.depends_on).every(([k, allowed]) => allowed.includes(S.answers[k]));
  }
  const L = (obj) => (obj && (obj[S.lang] || obj.en)) || "";

  function renderForm() {
    const wrap = qs("#form-live");
    const fields = fieldsInPlay();
    let html = "", sec = null;
    for (const f of fields) {
      if (f.section !== sec) { sec = f.section; html += `<h4>${esc(L(S.schema.sections[sec]))}</h4>`; }
      const val = S.answers[f.key];
      const filled = val !== undefined && val !== null;
      const cur = S.current && S.current.field_key === f.key;
      let input;
      if (f.type === "select") {
        input = `<select class="input" data-key="${f.key}"><option value="">—</option>${f.options.map((o) => `<option value="${esc(o.value)}" ${o.value === val ? "selected" : ""}>${esc(L(o.label))}</option>`).join("")}</select>`;
      } else if (f.type === "boolean") {
        input = `<select class="input" data-key="${f.key}"><option value="">—</option><option value="Y" ${val === "Y" ? "selected" : ""}>Yes</option><option value="N" ${val === "N" ? "selected" : ""}>No</option></select>`;
      } else if (f.type === "date") {
        input = `<input type="date" class="input" data-key="${f.key}" value="${esc(val || "")}" max="${new Date().toISOString().slice(0, 10)}">`;
      } else {
        const shown = filled ? (["pan", "aadhaar"].includes(f.type) ? S.display[f.key] : S.display[f.key] ?? val) : "";
        input = `<input class="input" data-key="${f.key}" value="${esc(shown)}" placeholder="${esc(f.placeholder || "")}" inputmode="${["number", "money", "phone", "pincode", "aadhaar"].includes(f.type) ? "numeric" : "text"}">`;
      }
      html += `<div class="ff ${filled ? "filled" : ""} ${cur ? "current" : ""}" id="ff-${f.key}"><label class="field-label">${esc(L(f.label))}</label>${input}<div class="err-t hidden"></div></div>`;
    }
    wrap.innerHTML = html;
    qsa("[data-key]", wrap).forEach((el) => el.addEventListener("change", () => editField(el.dataset.key, el.value, el)));
    const curEl = S.current && qs("#ff-" + S.current.field_key);
    if (curEl) curEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
    renderProgress();
  }

  function renderProgress() {
    const fields = fieldsInPlay();
    const done = fields.filter((f) => f.key in S.answers || S.skipped.includes(f.key)).length;
    const pct = Math.round((done / Math.max(1, fields.length)) * 100);
    qs("#prog-bar").style.width = pct + "%";
    qs("#prog-pct").textContent = pct + "%";
    const secs = {};
    fields.forEach((f) => {
      secs[f.section] = secs[f.section] || { total: 0, done: 0 };
      secs[f.section].total++;
      if (f.key in S.answers || S.skipped.includes(f.key)) secs[f.section].done++;
    });
    const allReq = fields.filter((f) => f.required).every((f) => f.key in S.answers);
    qs("#btn-to-review").classList.toggle("hidden", !allReq || !!S.current);
    const curSec = S.current && S.schema.fields.find((f) => f.key === S.current.field_key)?.section;
    qs("#sec-list").innerHTML = Object.entries(secs).map(([k, v]) =>
      `<li class="${v.done === v.total ? "done" : k === curSec ? "cur" : ""}"><span>${esc(L(S.schema.sections[k]))}</span><span>${v.done}/${v.total}</span></li>`).join("");
  }

  async function editField(key, raw, el) {
    const f = S.schema.fields.find((x) => x.key === key);
    const box = qs("#ff-" + key + " .err-t");
    if (raw === "" || raw == null) {
      if (f.required) return;
      delete S.answers[key]; delete S.display[key];
      return renderForm();
    }
    let res;
    if (f.type === "select") {
      const o = f.options.find((x) => x.value === raw);
      res = { success: true, normalized_value: raw, display_value: o ? o.label.en : raw };
    } else if (f.type === "boolean") {
      res = { success: true, normalized_value: raw, display_value: raw === "Y" ? "Yes" : "No" };
    } else {
      // masked display values (PAN/Aadhaar) can't be re-parsed; ignore unchanged
      if (raw === S.display[key]) return;
      res = await mapAnswer(key, raw);
    }
    if (!res.success) {
      box.textContent = res.error; box.classList.remove("hidden");
      el.classList.add("invalid");
      return;
    }
    if (["monthly_income", "loan_amount"].includes(key) && key in S.answers && S.answers[key] !== res.normalized_value) S.telemetry.income_corrections++;
    S.telemetry.typed_answers++;
    S.answers[key] = res.normalized_value;
    S.display[key] = res.display_value;
    S.skipped = S.skipped.filter((k) => k !== key);
    S.transcript.push({ role: "user", field: key, text: "[edited] " + raw, t: new Date().toISOString() });
    renderForm();
    qs("#ff-" + key)?.classList.add("flash");
    // if they filled the question being asked, move on
    if (S.current && S.current.field_key === key) { stopListening(); nextQuestion(); }
  }

  function mapAnswer(key, raw) {
    return api("/api/assistant/map-answer", {
      method: "POST",
      body: { field_key: key, raw_answer: raw, language: S.lang, context: { full_name: S.answers.full_name } },
    });
  }

  function addMsg(text, who = "ai", extra = "") {
    const el = document.createElement("div");
    el.className = `msg ${who} ${extra}`;
    el.innerHTML = text;
    qs("#msgs").appendChild(el);
    qs("#msgs").scrollTop = qs("#msgs").scrollHeight;
    return el;
  }

  function setVoiceState(s) {
    const mic = qs("#mic");
    mic.classList.toggle("listening", s === "listening");
    mic.classList.toggle("speaking", s === "speaking");
    qs("#voice-state").textContent = s === "listening" ? t("listening") : s === "speaking" ? t("speaking") : t("ready");
  }

  // ---------------- speech output
  let voices = [];
  function loadVoices() { voices = window.speechSynthesis ? speechSynthesis.getVoices() : []; }
  if (window.speechSynthesis) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }
  function pickVoice(lang) {
    const want = SPEECH_LANG[lang].toLowerCase();
    return voices.find((v) => v.lang.toLowerCase() === want)
      || voices.find((v) => v.lang.toLowerCase().startsWith(lang))
      || (lang === "en" ? voices.find((v) => v.lang.toLowerCase().startsWith("en")) : null);
  }
  function chunks(text, max = 180) {
    const parts = text.match(/[^.!?।]+[.!?।]?/g) || [text];
    const out = []; let cur = "";
    for (const p of parts) {
      if ((cur + p).length > max && cur) { out.push(cur.trim()); cur = ""; }
      cur += p;
    }
    if (cur.trim()) out.push(cur.trim());
    return out.flatMap((c) => (c.length > max ? c.match(new RegExp(`.{1,${max}}(\\s|$)`, "g")) : [c]));
  }
  const tts = new Audio();
  function playCloud(text) {
    return new Promise((resolve) => {
      tts.onended = tts.onerror = () => resolve();
      tts.src = `/api/tts?lang=${S.lang}&text=${encodeURIComponent(text)}`;
      tts.play().catch(() => resolve());
    });
  }
  async function speak(text) {
    if (!S.voiceOn || !text) return;
    const plain = text.replace(/<[^>]+>/g, "");
    S.speaking = true; setVoiceState("speaking");
    try {
      const voice = pickVoice(S.lang);
      if (voice && window.speechSynthesis) {
        speechSynthesis.cancel();
        for (const c of chunks(plain)) {
          await new Promise((resolve) => {
            const u = new SpeechSynthesisUtterance(c);
            u.voice = voice; u.lang = voice.lang; u.rate = S.lang === "en" ? 1 : 0.95;
            u.onend = u.onerror = () => resolve();
            const guard = setTimeout(resolve, 15000); // Chrome sometimes never fires onend
            u.onend = () => { clearTimeout(guard); resolve(); };
            speechSynthesis.speak(u);
          });
          if (!S.voiceOn) break;
        }
      } else {
        for (const c of chunks(plain)) { await playCloud(c); if (!S.voiceOn) break; }
      }
    } finally {
      S.speaking = false; setVoiceState("idle");
    }
  }
  function stopSpeaking() { try { speechSynthesis.cancel(); } catch {} tts.pause(); S.speaking = false; }

  // ---------------- speech input
  let rec = null;
  function listen() {
    if (!SR || !S.voiceOn || S.listening) return;
    rec = new SR();
    rec.lang = SPEECH_LANG[S.lang];
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    let finalText = "", gotAny = false;
    rec.onstart = () => { S.listening = true; setVoiceState("listening"); };
    rec.onresult = (e) => {
      gotAny = true;
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      qs("#interim").textContent = finalText || interim;
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        toast("Microphone blocked — you can type your answers.", "warn");
        S.voiceOn = false; updateVoiceBtn();
      }
    };
    const me = rec;
    rec.onend = () => {
      if (me._aborted) return;
      S.listening = false; setVoiceState("idle");
      const text = (finalText || qs("#interim").textContent || "").trim();
      qs("#interim").textContent = "";
      if (text) handleAnswer(text, "voice");
      else if (!gotAny && S.current && !S.busyAnswer) {
        S.retries++;
        if (S.retries >= 2) { addMsg(t("type_hint"), "ai", "err"); qs("#answer").focus(); }
      }
    };
    try { rec.start(); } catch { S.listening = false; }
  }
  function stopListening() {
    if (rec) { rec._aborted = true; if (S.listening) { try { rec.abort(); } catch {} } }
    S.listening = false; qs("#interim").textContent = ""; setVoiceState("idle");
  }

  function updateVoiceBtn() {
    const b = qs("#btn-voice-toggle");
    b.setAttribute("aria-pressed", String(S.voiceOn));
    b.style.opacity = S.voiceOn ? 1 : 0.45;
    qs("#mic").disabled = !SR || !S.voiceOn;
  }

  // ---------------- conversation
  const COMMANDS = {
    repeat: ["repeat", "again", "say again", "दोहराओ", "दोहराइए", "फिर से", "ಮತ್ತೆ", "ಮತ್ತೊಮ್ಮೆ", "ಪುನಃ"],
    back: ["back", "go back", "previous", "पीछे", "वापस", "ಹಿಂದೆ"],
  };
  const isCmd = (text, list) => list.includes(text.toLowerCase().trim().replace(/[.!?।]$/, ""));

  async function handleAnswer(text, via) {
    if (!S.current || S.busyAnswer) return;
    stopSpeaking();
    const key = S.current.field_key;
    if (isCmd(text, COMMANDS.repeat)) return askCurrent();
    if (isCmd(text, COMMANDS.back)) return goBack();
    S.busyAnswer = true;
    addMsg(`${esc(text)}<span class="via">${via === "voice" ? "🎙 voice" : "⌨ typed"}</span>`, "me");
    S.transcript.push({ role: "user", field: key, text, via, t: new Date().toISOString() });
    let res;
    try {
      res = await mapAnswer(key, text);
    } catch (e) {
      S.busyAnswer = false;
      addMsg(esc(e.message), "ai", "err");
      return;
    }
    S.busyAnswer = false;
    if (!res.success) {
      S.retries++;
      const msg = res.error + (S.retries >= 2 ? " " + t("type_hint") : "");
      addMsg(esc(msg), "ai", "err");
      S.transcript.push({ role: "assistant", text: msg, t: new Date().toISOString() });
      await speak(res.error);
      if (S.retries < 3 && via === "voice") listen(); else qs("#answer").focus();
      return;
    }
    S.retries = 0;
    via === "voice" ? S.telemetry.voice_answers++ : S.telemetry.typed_answers++;
    if (res.skipped) { S.skipped.push(key); }
    else {
      S.answers[key] = res.normalized_value;
      S.display[key] = res.display_value;
    }
    S.history.push(key);
    const shown = res.skipped ? "Skipped" : (res.display_i18n ? L(res.display_i18n) : res.display_value);
    addMsg(`✓ ${esc(L(fieldByKey(key).label))}: <b>${esc(shown)}</b>`, "ai", "ok-ack");
    (res.warnings || []).forEach((w) => addMsg("⚠ " + esc(w), "ai", "err"));
    renderForm();
    qs("#ff-" + key)?.classList.add("flash");
    nextQuestion(true);
  }

  const fieldByKey = (k) => S.schema.fields.find((f) => f.key === k);

  async function goBack() {
    const prev = S.history.pop();
    if (!prev) return askCurrent();
    delete S.answers[prev]; delete S.display[prev];
    S.skipped = S.skipped.filter((k) => k !== prev);
    S.current = null;
    nextQuestion();
  }

  async function nextQuestion(ack = false) {
    let q;
    try {
      q = await api("/api/assistant/next-question", {
        method: "POST",
        body: { language: S.lang, field_keys: S.fieldKeys, answers: S.answers, skipped: S.skipped },
      });
    } catch (e) {
      addMsg(esc(e.message), "ai", "err");
      return;
    }
    if (q.completed) {
      S.current = null;
      renderForm();
      addMsg(esc(t("done")));
      await speak(t("done"));
      openReview();
      return;
    }
    S.current = q;
    renderForm();
    askCurrent(ack);
  }

  async function askCurrent(ack = false) {
    const q = S.current;
    if (!q) return;
    S.retries = 0;
    addMsg(esc(q.question_text) + (q.required ? "" : ' <span class="muted small">(optional)</span>'));
    S.transcript.push({ role: "assistant", field: q.field_key, text: q.question_text, t: new Date().toISOString() });
    renderQuick(q);
    qs("#answer").value = "";
    await speak((ack ? t("got") + ". " : "") + q.question_text);
    if (S.current === q && !S.busyAnswer) listen();
  }

  function renderQuick(q) {
    const f = fieldByKey(q.field_key);
    let opts = [];
    if (f.type === "select") opts = f.options.map((o) => L(o.label));
    if (f.type === "boolean") opts = S.lang === "hi" ? ["हाँ", "नहीं"] : S.lang === "kn" ? ["ಹೌದು", "ಇಲ್ಲ"] : ["Yes", "No"];
    if (f.key === "loan_tenure_months") opts = ["12", "24", "36", "48", "60"];
    if (f.key === "dependents") opts = ["0", "1", "2", "3", "4"];
    if (f.key === "existing_emi") opts = ["0"];
    const ctl = [t("repeat"), t("back")].concat(f.required ? [] : [t("skip")]);
    qs("#quick").innerHTML = opts.map((o) => `<button type="button" data-a="${esc(o)}">${esc(o)}</button>`).join("") +
      ctl.map((o, i) => `<button type="button" data-c="${i}" style="border-style:dashed">${esc(o)}</button>`).join("");
    qsa("#quick [data-a]").forEach((b) => b.addEventListener("click", () => { stopListening(); handleAnswer(b.dataset.a, "typed"); }));
    qsa("#quick [data-c]").forEach((b) => b.addEventListener("click", () => {
      stopListening();
      const i = +b.dataset.c;
      if (i === 0) askCurrent(); else if (i === 1) goBack(); else handleAnswer("skip", "typed");
    }));
  }

  async function startInterview() {
    if (liveRun) liveRun.cancel();
    go("interview");
    if (S.stream) {
      qs("#video2").srcObject = S.stream;
      if (S.faceReady) {
        S.monitor = FaceKit.monitor(qs("#video2"), {
          onUpdate: (n) => {
            const tag = qs("#mon-tag");
            tag.className = "tag pill " + (n === 1 ? "ok" : n === 0 ? "warn" : "bad");
            tag.innerHTML = `<span class="dot"></span>${n === 1 ? "You're on camera" : n === 0 ? "Face not visible" : n + " faces in view"}`;
          },
        });
        S.monitor.start();
      }
    }
    qs("#answer").placeholder = t("placeholder");
    updateVoiceBtn();
    setVoiceState("idle");
    renderForm();
    addMsg(esc(t("welcome")));
    await speak(t("welcome"));
    nextQuestion();
  }

  function initInterview() {
    qs("#composer").addEventListener("submit", (e) => {
      e.preventDefault();
      const v = qs("#answer").value.trim();
      if (!v) return;
      stopListening();
      qs("#answer").value = "";
      handleAnswer(v, "typed");
    });
    qs("#answer").addEventListener("focus", () => { stopListening(); });
    qs("#mic").addEventListener("click", () => {
      if (S.listening) return stopListening();
      stopSpeaking();
      S.retries = 0;
      listen();
    });
    qs("#btn-to-review").addEventListener("click", openReview);
    qs("#btn-voice-toggle").addEventListener("click", () => {
      S.voiceOn = !S.voiceOn;
      if (!S.voiceOn) { stopSpeaking(); stopListening(); }
      updateVoiceBtn();
    });
  }

  // ------------------------------------------------------------------ review
  function openReview() {
    stopListening(); stopSpeaking();
    if (S.monitor) {
      const snap = S.monitor.snapshot();
      S.verification.face_presence_ratio = snap.presence;
      S.verification.max_faces_seen = snap.frames ? snap.maxFaces : null;
      S.verification.estimated_age = snap.age;
    }
    const fields = fieldsInPlay();
    const bySec = {};
    fields.forEach((f) => (bySec[f.section] = bySec[f.section] || []).push(f));
    qs("#review-body").innerHTML = Object.entries(bySec).map(([sec, fs]) => `
      <div class="review-sec"><div class="kicker" style="margin:14px 0 6px">${esc(L(S.schema.sections[sec]))}</div>
      <table class="t"><tbody>${fs.map((f) => {
        const v = f.key in S.answers ? S.display[f.key] ?? S.answers[f.key] : S.skipped.includes(f.key) ? "Skipped" : "";
        const missing = f.required && !(f.key in S.answers);
        return `<tr><td>${esc(L(f.label))}</td><td><b style="${missing ? "color:var(--bad)" : ""}">${missing ? "Missing" : esc(v)}</b></td>
          <td style="text-align:right"><button class="btn sm ghost" data-edit="${f.key}">Edit</button></td></tr>`;
      }).join("")}</tbody></table></div>`).join("");
    qsa("[data-edit]").forEach((b) => b.addEventListener("click", () => {
      go("interview");
      const el = qs(`#ff-${b.dataset.edit} .input`);
      el?.scrollIntoView({ block: "center" });
      el?.focus();
    }));
    const v = S.verification;
    const item = (ok, title, detail) => `<li class="${ok === true ? "pass" : ok === false ? "fail" : "warn"}"><span class="ic">${ok === true ? "✓" : ok === false ? "✕" : "!"}</span><div><b>${title}</b><span class="small muted">${detail}</span></div></li>`;
    qs("#ver-list").innerHTML = [
      item(v.liveness_passed === true ? true : v.liveness_passed === false ? false : null, "Liveness", v.liveness_passed ? "Blink & head-turn passed" : "Not completed"),
      item(v.face_match_score == null ? null : v.face_match_score >= 0.6 ? true : v.face_match_score >= 0.45 ? null : false, "Face vs ID photo", v.face_match_score == null ? "Not done" : Math.round(v.face_match_score * 100) + "% similarity"),
      item(v.max_faces_seen == null ? null : v.max_faces_seen <= 1, "Single person on camera", v.max_faces_seen == null ? "Camera off" : v.max_faces_seen + " max faces seen"),
      item(S.geo.city ? true : null, "Device location", S.geo.city ? `${S.geo.city}, ${S.geo.state}` : "Not shared"),
      item(true, "Consent", "Recorded " + new Date(S.consentAt).toLocaleTimeString()),
    ].join("");
    qs("#c-final").checked = false;
    qs("#btn-submit").disabled = true;
    go("review");
  }

  function initReview() {
    qs("#c-final").addEventListener("change", (e) => (qs("#btn-submit").disabled = !e.target.checked));
    qs("#btn-back-iv").addEventListener("click", () => go("interview"));
    qs("#btn-submit").addEventListener("click", submit);
  }

  async function submit() {
    const missing = fieldsInPlay().filter((f) => f.required && !(f.key in S.answers));
    if (missing.length) return toast("Please fill: " + missing.map((f) => L(f.label)).join(", "), "warn");
    qs("#btn-submit").disabled = true;
    const busy = qs("#busy");
    busy.classList.remove("hidden");
    const lis = qsa("#busy-steps li");
    let i = 0;
    const tick = setInterval(() => { lis.forEach((li, j) => { li.className = j < i ? "done" : j === i ? "on" : ""; }); i = Math.min(i + 1, lis.length); }, 450);
    try {
      const body = {
        session_id: S.sessionId,
        language: S.lang,
        answers: S.answers,
        verification: S.verification,
        geo: S.geo,
        consent: { given: true, timestamp: S.consentAt, version: "v1-video-kyc-bureau-transcript" },
        telemetry: S.telemetry,
        transcript: S.transcript,
      };
      const [res] = await Promise.all([
        api("/api/session/complete", { method: "POST", body, timeout: 60000 }),
        new Promise((r) => setTimeout(r, 1900)), // let the steps animate
      ]);
      clearInterval(tick);
      try { sessionStorage.setItem("credai:" + res.application_id, JSON.stringify(res)); } catch {}
      stopCamera();
      S.submitted = true;
      location.href = "result.html?id=" + encodeURIComponent(res.application_id);
    } catch (e) {
      clearInterval(tick);
      busy.classList.add("hidden");
      qs("#btn-submit").disabled = false;
      toast(e.message, "bad");
    }
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    Cred.healthPill(qs("#health"));
    initStart(); initIdentity(); initInterview(); initReview();
    try {
      S.schema = await api("/api/form/schema");
    } catch (e) {
      toast(e.message, "bad");
      qs("#btn-begin").textContent = "Server unavailable — refresh to retry";
    }
    // load face models + warm up GPU while the user reads the consent page
    const onStartPage = () => !qs("#step-start").classList.contains("hidden");
    setTimeout(() => FaceKit.load().then(() => FaceKit.warmHeavy(onStartPage)).catch(() => {}), 600);
    window.addEventListener("pagehide", stopCamera);
    const urlLang = new URLSearchParams(location.search).get("lang");
    if (urlLang && ["en", "hi", "kn"].includes(urlLang)) qs(`#lang-seg [data-lang="${urlLang}"]`).click();
    window.addEventListener("beforeunload", (e) => {
      if (S.sessionId && Object.keys(S.answers).length && !S.submitted) { e.preventDefault(); e.returnValue = ""; }
    });
  }
  boot();
})();
