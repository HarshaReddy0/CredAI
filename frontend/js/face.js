/* Browser-side face engine (face-api.js, models served locally from /vendor).
   Performance notes (v2.1):
   - liveness loop uses the 80 KB *tiny* landmark model, throttled to ~8 fps and
     adapted to device speed, instead of running full recognition every frame
   - 128-d face descriptors (heavy) are computed only a few times, never per frame
   - models load + GPU shaders warm up in the background while the user reads the
     consent page, so step 2 starts instantly */
(function () {
  const MODEL_URL = "vendor/face-api/model";
  let loaded = null;
  let backend = "webgl";
  let status = "idle"; // idle | loading | ready | error
  const listeners = new Set();
  const setStatus = (s, detail) => { status = s; listeners.forEach((fn) => fn(s, detail)); };

  async function load() {
    if (loaded) return loaded;
    loaded = (async () => {
      if (!window.faceapi) throw new Error("face engine script failed to load");
      setStatus("loading", "Loading face models…");
      try { await faceapi.tf.setBackend("webgl"); await faceapi.tf.ready(); backend = "webgl"; }
      catch { await faceapi.tf.setBackend("cpu"); await faceapi.tf.ready(); backend = "cpu"; }
      if (faceapi.tf.getBackend() !== "webgl") backend = "cpu";
      // light models first so liveness can start as soon as possible
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        faceapi.nets.faceLandmark68TinyNet.loadFromUri(MODEL_URL),
      ]);
      setStatus("loading", "Preparing camera AI…");
      await warmUp();
      setStatus("ready");
      // heavier models in the background (needed only for face match / age)
      heavy = Promise.all([
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
        faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
        faceapi.nets.ageGenderNet.loadFromUri(MODEL_URL),
      ]);
      return true;
    })();
    try { return await loaded; } catch (e) { loaded = null; setStatus("error", e.message); throw e; }
  }
  let heavy = null, warmed = false;
  async function loadHeavy() { await load(); return heavy; }
  /** Compile heavy-net shaders while idle. Caller decides when it's safe (e.g. still on the consent page). */
  async function warmHeavy(stillIdle = () => true) {
    if (warmed) return;
    await loadHeavy();
    const c = document.createElement("canvas");
    c.width = c.height = 150;
    c.getContext("2d").fillRect(0, 0, 150, 150);
    const steps = [
      () => faceapi.nets.faceLandmark68Net.detectLandmarks(c),
      () => faceapi.nets.faceRecognitionNet.computeFaceDescriptor(c),
      () => faceapi.nets.ageGenderNet.predictAgeAndGender(c),
    ];
    for (const st of steps) {
      if (!stillIdle()) return; // user moved on; don't freeze the live challenge
      try { await st(); } catch {}
      await sleep(80);
    }
    warmed = true;
  }

  async function warmUp() {
    // first inference compiles WebGL shaders (can freeze 1-3 s) — do it on a blank canvas, not the live video
    // warm every input size we use later so no shader compiles during the live challenge
    const c = document.createElement("canvas");
    c.width = 640; c.height = 480;
    const g = c.getContext("2d"); g.fillStyle = "#888"; g.fillRect(0, 0, 640, 480);
    for (const size of [224, 160]) {
      try { await faceapi.detectAllFaces(c, opts(size, 0.4)).withFaceLandmarks(true); } catch { /* ignore */ }
      await sleep(0);
    }
  }

  const slow = () => backend !== "webgl";
  const opts = (size = 224, thr = 0.45) =>
    new faceapi.TinyFaceDetectorOptions({ inputSize: slow() ? Math.min(size, 160) : size, scoreThreshold: thr });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  function ear(eye) { return (dist(eye[1], eye[5]) + dist(eye[2], eye[4])) / (2 * dist(eye[0], eye[3])); }
  function poseFrom(lm) {
    const jaw = lm.getJawOutline(), nose = lm.getNose()[3];
    const raw = (nose.x - jaw[0].x) / Math.max(1, jaw[16].x - jaw[0].x);
    return { yaw: 1 - raw, ear: (ear(lm.getLeftEye()) + ear(lm.getRightEye())) / 2 };
  }

  /** Randomised liveness challenge. onStep(stepKey, state); onFrame(results) for drawing. */
  function liveness(video, { onStep, onFrame, timeoutMs = 60000 } = {}) {
    const order = Math.random() < 0.5 ? ["blink", "left", "right"] : ["blink", "right", "left"];
    if (Math.random() < 0.5) order.push(order.shift());
    let idx = 0, baseline = 0, closed = false, stop = false, frames = 0;
    const started = performance.now();
    const targetFrameMs = slow() ? 220 : 110; // ~4.5 fps on CPU, ~9 fps on GPU

    return {
      order,
      cancel() { stop = true; },
      promise: new Promise((resolve) => {
        onStep && onStep(order[0], { index: 0, total: order.length });
        const tick = async () => {
          if (stop) return resolve({ passed: false, reason: "cancelled" });
          if (performance.now() - started > timeoutMs) return resolve({ passed: false, reason: "timeout", completed: idx, order });
          const t0 = performance.now();
          let res = [];
          if (video.readyState >= 2 && !document.hidden) {
            try { res = await faceapi.detectAllFaces(video, opts(224, 0.4)).withFaceLandmarks(true); } catch { res = []; }
            frames++;
          }
          onFrame && onFrame(res);
          if (res.length === 1) {
            const p = poseFrom(res[0].landmarks);
            baseline = Math.max(baseline * 0.99, p.ear);
            const want = order[idx];
            let ok = false;
            if (want === "blink") {
              if (p.ear < baseline * 0.75) closed = true;
              else if (closed && p.ear > baseline * 0.85) ok = true;
            } else if (want === "left") ok = p.yaw < 0.37;
            else if (want === "right") ok = p.yaw > 0.63;
            if (ok) {
              idx++; closed = false;
              if (idx >= order.length) return resolve({ passed: true, order, frames });
              onStep && onStep(order[idx], { index: idx, total: order.length });
              await sleep(400);
            }
          }
          // adapt to device speed: never hog the main thread
          const spent = performance.now() - t0;
          setTimeout(tick, Math.max(30, targetFrameMs - spent) + (spent > 250 ? 120 : 0));
        };
        tick();
      }),
    };
  }

  function averageDescriptor(list) {
    if (!list.length) return null;
    const out = new Array(128).fill(0);
    list.forEach((d) => d.forEach((v, i) => (out[i] += v / list.length)));
    return out;
  }

  /** A few frontal samples of the live face → one averaged descriptor. */
  async function liveDescriptor(video, samples = 3, maxTries = 10) {
    await loadHeavy();
    const got = [];
    for (let i = 0; i < maxTries && got.length < samples; i++) {
      try {
        const r = await faceapi.detectSingleFace(video, opts(320, 0.5)).withFaceLandmarks().withFaceDescriptor();
        if (r) got.push(Array.from(r.descriptor));
      } catch { /* dropped frame */ }
      await sleep(250);
    }
    return averageDescriptor(got);
  }

  /** Face printed on an ID card (small) — try larger input sizes. Downscale huge photos first. */
  async function idDescriptor(img) {
    await loadHeavy();
    const src = downscale(img, 1280);
    for (const size of [608, 416, 320]) {
      const all = await faceapi.detectAllFaces(src, new faceapi.TinyFaceDetectorOptions({ inputSize: size, scoreThreshold: 0.3 }))
        .withFaceLandmarks().withFaceDescriptors();
      if (all.length) {
        all.sort((a, b) => b.detection.box.area - a.detection.box.area);
        return { descriptor: Array.from(all[0].descriptor), faces: all.length };
      }
      await sleep(0);
    }
    return null;
  }

  function downscale(img, max) {
    const w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
    if (Math.max(w, h) <= max) return img;
    const k = max / Math.max(w, h), c = document.createElement("canvas");
    c.width = Math.round(w * k); c.height = Math.round(h * k);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return c;
  }

  function matchScore(a, b) {
    if (!a || !b) return null;
    const d = faceapi.euclideanDistance(a, b);
    return { distance: +d.toFixed(3), score: +Math.max(0, Math.min(1, 1 - d / 1.25)).toFixed(3) };
  }

  /** Lightweight monitor during the interview (every 2 s; age only every 4th sample). */
  function monitor(video, { intervalMs = 2000, onUpdate } = {}) {
    const st = { frames: 0, withFace: 0, maxFaces: 0, ages: [] };
    let timer = null, busy = false;
    const loop = async () => {
      if (busy || video.readyState < 2 || document.hidden) return;
      busy = true;
      try {
        const res = await faceapi.detectAllFaces(video, opts(160, 0.45));
        st.frames++;
        if (res.length) st.withFace++;
        st.maxFaces = Math.max(st.maxFaces, res.length);
        if (res.length === 1 && st.frames % 4 === 1 && st.ages.length < 15 && faceapi.nets.ageGenderNet.isLoaded) {
          const ag = await faceapi.detectSingleFace(video, opts(224, 0.5)).withAgeAndGender();
          if (ag) st.ages.push(ag.age);
        }
        onUpdate && onUpdate(res.length, snapshot());
      } catch { /* ignore */ }
      busy = false;
    };
    function snapshot() {
      const ages = [...st.ages].sort((a, b) => a - b);
      return {
        presence: st.frames ? st.withFace / st.frames : null,
        maxFaces: st.maxFaces,
        age: ages.length ? Math.round(ages[Math.floor(ages.length / 2)]) : null,
        frames: st.frames,
      };
    }
    return { start() { if (!timer) timer = setInterval(loop, intervalMs); }, stop() { clearInterval(timer); timer = null; }, snapshot };
  }

  window.FaceKit = {
    load, loadHeavy, warmHeavy, liveness, liveDescriptor, idDescriptor, matchScore, monitor,
    get status() { return status; }, get backend() { return backend; },
    onStatus(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  };
})();
