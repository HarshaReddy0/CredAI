(function () {
  const { api, esc, inr, lakh, toast, fmtDate, qs, qsa, DECISION } = window.Cred;
  const COLORS = { APPROVED: "#047857", PARTIALLY_APPROVED: "#14b8a6", MANUAL_REVIEW: "#d97706", REJECTED: "#b91c1c" };
  let key = sessionStorage.getItem("credai:admin") || "";
  let tab = "all", rows = [], timer;

  const adminApi = (path, opts = {}) => api(path, { ...opts, headers: { ...(opts.headers || {}), "X-Admin-Key": key } });

  async function guarded(fn) {
    try { return await fn(); }
    catch (e) {
      if (e.status === 401) { askKey(); throw e; }
      toast(e.message, "bad"); throw e;
    }
  }
  function askKey() {
    qs("#key-modal").classList.remove("hidden");
    setTimeout(() => qs("#key-input").focus(), 50);
  }
  qs("#key-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    key = qs("#key-input").value.trim();
    try {
      await adminApi("/api/admin/auth");
      sessionStorage.setItem("credai:admin", key);
      qs("#key-modal").classList.add("hidden");
      load();
    } catch { toast("Wrong admin key", "bad"); }
  });

  function decisionPill(dcs) {
    const d = DECISION[dcs] || { label: dcs, cls: "info" };
    return `<span class="pill ${d.cls}"><span class="dot"></span>${esc(d.label)}</span>`;
  }
  const fraudPill = (lvl, s) => `<span class="pill ${lvl === "CLEAN" || lvl === "LOW" ? "ok" : lvl === "MEDIUM" ? "warn" : "bad"}">${s ?? ""} ${esc(lvl)}</span>`;

  function renderStats(s) {
    qs("#kpis").innerHTML = [
      ["Applications", s.total, `${lakh(s.total_requested)} requested`],
      ["Approval rate", s.approval_rate + "%", `${s.approved} approved`],
      ["In review", s.review, "awaiting underwriter"],
      ["Avg CredAI score", s.avg_credit_score || "—", `${s.blocked} high fraud risk`],
    ].map(([l, v, sub]) => `<div class="card kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${sub}</div></div>`).join("");
    qs("#q-count").textContent = s.review;

    // donut
    const entries = Object.entries(s.by_decision || {});
    const total = entries.reduce((a, [, v]) => a + v, 0);
    if (!total) qs("#donut").innerHTML = '<div class="empty" style="width:100%">No applications yet. <a href="apply.html">Create the first one →</a></div>';
    else {
      let acc = 0; const C = 2 * Math.PI * 40;
      const arcs = entries.map(([k, v]) => {
        const len = (v / total) * C, el = `<circle r="40" cx="60" cy="60" fill="none" stroke="${COLORS[k] || "#94a3b8"}" stroke-width="18" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-acc}" transform="rotate(-90 60 60)"/>`;
        acc += len; return el;
      }).join("");
      qs("#donut").innerHTML = `<svg viewBox="0 0 120 120" width="140">${arcs}<text x="60" y="64" text-anchor="middle" font-weight="800" font-size="18">${total}</text></svg>
        <div class="legend" style="flex-direction:column">${entries.map(([k, v]) => `<span><i style="background:${COLORS[k]}"></i>${esc((DECISION[k] || {}).label || k)} — <b>${v}</b></span>`).join("")}</div>`;
    }
    const days = Object.entries(s.daily || {});
    const max = Math.max(1, ...days.map(([, v]) => v));
    qs("#daily").innerHTML = days.length ? days.map(([d, v]) => `<div class="b" style="height:${(v / max) * 100}%"><em>${v}</em><span>${d.slice(5)}</span></div>`).join("") : '<div class="empty" style="width:100%">No data yet</div>';
  }

  function renderRows() {
    const q = qs("#search").value.trim().toLowerCase(), f = qs("#filter").value;
    let list = rows;
    if (tab === "MANUAL_REVIEW") list = list.filter((r) => r.decision === "MANUAL_REVIEW");
    if (tab === "fraud") list = list.filter((r) => ["MEDIUM", "HIGH"].includes(r.fraud_level));
    if (f) list = list.filter((r) => r.decision === f);
    if (q) list = list.filter((r) => [r.id, r.name, r.city, r.phone].some((x) => (x || "").toLowerCase().includes(q)));
    qs("#rows").innerHTML = list.length ? list.map((r) => `
      <tr class="click" data-id="${esc(r.id)}">
        <td class="mono small">${esc(r.id)}${r.status === "REVIEWED" ? ' <span class="pill info" style="padding:0 6px">reviewed</span>' : ""}</td>
        <td><b>${esc(r.name || "—")}</b><div class="small muted">${esc(r.city || "")}</div></td>
        <td>${inr(r.loan_amount)}</td>
        <td><b>${r.credit_score ?? "—"}</b></td>
        <td><span class="small">${esc(r.risk_band || "")}</span><div class="small muted">PD ${r.risk_score}%</div></td>
        <td>${fraudPill(r.fraud_level, r.fraud_score)}</td>
        <td>${decisionPill(r.decision)}</td>
        <td class="small muted">${fmtDate(r.created_at)}</td>
      </tr>`).join("") : `<tr><td colspan="8" class="empty">No applications match.</td></tr>`;
    qsa("#rows tr[data-id]").forEach((tr) => tr.addEventListener("click", () => openDrawer(tr.dataset.id)));
  }

  async function openDrawer(id) {
    const wrap = qs("#drawer-wrap"), el = qs("#drawer");
    wrap.classList.remove("hidden");
    el.innerHTML = '<div class="skeleton" style="height:120px"></div>';
    let r;
    try { r = await guarded(() => adminApi("/api/admin/applications/" + encodeURIComponent(id))); } catch { wrap.classList.add("hidden"); return; }
    const a = r.applicant, d = r.decision, risk = r.risk_assessment, fr = r.fraud_assessment;
    el.innerHTML = `
      <div class="row between"><span class="mono small muted">${esc(r.application_id)}</span><button class="icon-btn" id="d-close" aria-label="Close">✕</button></div>
      <h2>${esc(a.full_name)}</h2>
      <div class="row wrap" style="margin-bottom:14px">${decisionPill(r.final_decision)}${fraudPill(fr.fraud_level, fr.fraud_score)}<span class="pill">Score ${risk.credit_score}</span><span class="pill">PD ${risk.probability_of_default}%</span></div>
      <div class="card tight"><h3>Underwriter action</h3>
        <textarea class="input" id="d-note" rows="2" placeholder="Note (visible in the audit trail)">${esc(r.reviewer_note || "")}</textarea>
        <div class="row wrap" style="margin-top:10px"><button class="btn sm ok" data-set="APPROVED">Approve</button><button class="btn sm danger" data-set="REJECTED">Reject</button><button class="btn sm ghost" data-set="MANUAL_REVIEW">Keep in review</button>
        <a class="btn sm ghost" href="/api/applications/${encodeURIComponent(r.application_id)}/report.pdf">PDF report</a><a class="btn sm ghost" href="result.html?id=${encodeURIComponent(r.application_id)}" target="_blank">Applicant view</a></div>
      </div>
      <div class="grid g2" style="margin-top:14px">
        <div class="card tight"><h3>Applicant</h3><dl class="kv">
          <dt>Age</dt><dd>${Math.round(a.age_years)}</dd><dt>Mobile</dt><dd>${esc(a.phone)}</dd><dt>City</dt><dd>${esc(a.city)}, ${esc(a.state || "")}</dd>
          <dt>Employment</dt><dd>${esc(r.profile?.employment || a.employment_type)}</dd><dt>Employer</dt><dd>${esc(a.employer_name || "—")}</dd>
          <dt>Income</dt><dd>${inr(a.monthly_income)}/mo</dd><dt>Existing EMI</dt><dd>${inr(a.existing_emi)}</dd><dt>CIBIL</dt><dd>${a.cibil_score ?? "Not given"}</dd>
          <dt>PAN</dt><dd class="mono">${esc(a.pan_masked)}</dd><dt>Aadhaar</dt><dd class="mono">${esc(a.aadhaar_masked || "—")}</dd></dl></div>
        <div class="card tight"><h3>Loan</h3><dl class="kv">
          <dt>Requested</dt><dd>${inr(d.requested_amount)}</dd><dt>Max eligible</dt><dd>${inr(d.max_eligible_amount)}</dd><dt>Approved</dt><dd>${inr(d.approved_amount)}</dd>
          <dt>Tenure</dt><dd>${d.tenure_months} m</dd><dt>Rate</dt><dd>${d.interest_rate}%</dd><dt>FOIR after</dt><dd>${d.affordability.foir_after_pct}%</dd></dl>
          <div class="small muted" style="margin-top:8px">${esc(r.profile?.summary || "")}</div></div>
      </div>
      <div class="card tight" style="margin-top:14px"><h3>Reasons &amp; conditions</h3>${[...d.reasons, ...d.conditions].map((x) => `<div class="small" style="margin:4px 0">• ${esc(x)}</div>`).join("")}</div>
      <div class="card tight" style="margin-top:14px"><h3>Fraud checks</h3><ul class="checks">${fr.checks.map((c) => `<li class="${c.status}"><span class="ic">${{ pass: "✓", warn: "!", fail: "✕", skipped: "–" }[c.status]}</span><div><b>${esc(c.check)} ${c.points ? `<span class="muted">+${c.points}</span>` : ""}</b><span class="small muted">${esc(c.detail)}</span></div></li>`).join("")}</ul></div>
      <div class="card tight" style="margin-top:14px"><h3>Transcript</h3><div style="max-height:260px;overflow:auto" class="small">${(r.transcript || []).map((m) => `<div style="margin:4px 0"><b style="color:${m.role === "user" ? "var(--brand)" : "var(--muted)"}">${m.role === "user" ? "Applicant" : "Asha"}:</b> ${esc(m.text)}</div>`).join("") || '<span class="muted">No transcript</span>'}</div></div>
      <div class="card tight" style="margin-top:14px"><h3>Audit trail</h3>${(r.audit_trail || []).map((e) => `<div class="small" style="margin:3px 0"><span class="mono muted">${fmtDate(e.t)}</span> — ${esc(e.event)}${e.note ? ` <i class="muted">“${esc(e.note)}”</i>` : ""}</div>`).join("")}</div>`;
    qs("#d-close").addEventListener("click", () => wrap.classList.add("hidden"));
    qsa("[data-set]", el).forEach((b) => b.addEventListener("click", async () => {
      try {
        await guarded(() => adminApi(`/api/admin/applications/${encodeURIComponent(r.application_id)}/decision`, { method: "POST", body: { decision: b.dataset.set, note: qs("#d-note").value } }));
        toast("Decision saved", "ok");
        wrap.classList.add("hidden");
        load();
      } catch {}
    }));
  }
  qs("#drawer-wrap").addEventListener("click", (e) => { if (e.target.id === "drawer-wrap") e.currentTarget.classList.add("hidden"); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") qs("#drawer-wrap").classList.add("hidden"); });

  async function load() {
    try {
      const [s, list] = await guarded(() => Promise.all([adminApi("/api/admin/stats"), adminApi("/api/admin/applications?limit=500")]));
      renderStats(s);
      rows = list.applications;
      renderRows();
      qs("#refresh-info").textContent = "Updated " + new Date().toLocaleTimeString();
    } catch {}
  }

  qsa(".tabs button").forEach((b) => b.addEventListener("click", () => {
    qsa(".tabs button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    tab = b.dataset.tab; renderRows();
  }));
  qs("#search").addEventListener("input", renderRows);
  qs("#filter").addEventListener("change", renderRows);
  qs("#btn-refresh").addEventListener("click", load);
  qs("#btn-export").addEventListener("click", () => {
    const cols = ["id", "created_at", "name", "phone", "city", "loan_amount", "decision", "credit_score", "risk_score", "risk_band", "fraud_score", "fraud_level", "status"];
    const csv = [cols.join(",")].concat(rows.map((r) => cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","))).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "credai-applications.csv"; a.click();
  });

  Cred.healthPill(qs("#health"));
  load();
  timer = setInterval(() => { if (!document.hidden && qs("#drawer-wrap").classList.contains("hidden")) load(); }, 15000);
})();
