/* Shared helpers for every CredAI page. No build step, no framework. */
(function () {
  const API = window.CREDAI_API_BASE || ""; // same origin by default

  async function api(path, { method = "GET", body, headers = {}, timeout = 30000, raw = false } = {}) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeout);
    const opts = { method, headers: { ...headers }, signal: ctrl.signal };
    if (body instanceof FormData) opts.body = body;
    else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
    try {
      const res = await fetch(API + path, opts);
      if (raw) return res;
      const isJson = (res.headers.get("content-type") || "").includes("json");
      const data = isJson ? await res.json() : await res.text();
      if (!res.ok) {
        const d = data && data.detail;
        const msg = (d && (d.errors ? d.errors.join(" ") : d.message || d)) || `Request failed (${res.status})`;
        const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        err.status = res.status; err.data = data;
        throw err;
      }
      return data;
    } catch (e) {
      if (e.name === "AbortError") throw new Error("The server took too long to respond. Please try again.");
      if (e instanceof TypeError) throw new Error("Can't reach the CredAI server. Is the backend running?");
      throw e;
    } finally { clearTimeout(t); }
  }

  function inr(n, opts = {}) {
    const v = Math.round(Number(n) || 0);
    return (opts.symbol === false ? "" : "₹") + v.toLocaleString("en-IN");
  }
  function lakh(n) {
    n = Number(n) || 0;
    if (n >= 1e7) return "₹" + (n / 1e7).toFixed(n % 1e7 ? 2 : 0) + " Cr";
    if (n >= 1e5) return "₹" + (n / 1e5).toFixed(n % 1e5 ? 2 : 0).replace(/\.?0+$/, "") + " L";
    return inr(n);
  }
  function emi(p, rate, months) {
    const r = rate / 1200;
    if (!p || !months) return 0;
    if (!r) return p / months;
    return (p * r * Math.pow(1 + r, months)) / (Math.pow(1 + r, months) - 1);
  }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function toast(msg, type = "") {
    let box = document.querySelector(".toasts");
    if (!box) { box = document.createElement("div"); box.className = "toasts"; box.setAttribute("role", "status"); document.body.appendChild(box); }
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; setTimeout(() => el.remove(), 300); }, 3800);
  }
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
  }
  const DECISION = {
    APPROVED: { label: "Approved", cls: "ok" },
    PARTIALLY_APPROVED: { label: "Approved (lower amount)", cls: "ok" },
    MANUAL_REVIEW: { label: "Under review", cls: "warn" },
    REJECTED: { label: "Not approved", cls: "bad" },
  };
  const qs = (s, el = document) => el.querySelector(s);
  const qsa = (s, el = document) => [...el.querySelectorAll(s)];

  async function healthPill(el) {
    if (!el) return;
    try {
      const h = await api("/api/health", { timeout: 6000 });
      el.className = "pill " + (h.models_loaded ? "ok" : "warn");
      el.innerHTML = `<span class="dot"></span>${h.models_loaded ? "AI engine online" : "Model not loaded"}`;
    } catch {
      el.className = "pill bad";
      el.innerHTML = `<span class="dot"></span>Server offline`;
    }
  }

  window.Cred = { api, inr, lakh, emi, esc, toast, fmtDate, DECISION, qs, qsa, healthPill };
})();
