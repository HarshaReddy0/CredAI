(function () {
  const { api, esc, inr, lakh, emi, toast, fmtDate, qs, qsa, DECISION } = window.Cred;
  const id = new URLSearchParams(location.search).get("id");
  const PURPOSE = { education: "education", medical: "medical needs", home_improvement: "home improvement", business: "your business", wedding: "the wedding", vehicle: "a vehicle", agriculture: "agriculture", debt_consolidation: "consolidating loans", travel: "travel", personal: "personal needs" };

  function gauge(score) {
    const min = 300, max = 900, pct = (score - min) / (max - min);
    const a = Math.PI * (1 - pct), r = 80, cx = 100, cy = 95;
    const x = cx + r * Math.cos(a), y = cy - r * Math.sin(a);
    const color = score >= 750 ? "var(--ok)" : score >= 650 ? "#65a30d" : score >= 550 ? "var(--warn)" : "var(--bad)";
    const label = score >= 750 ? "Excellent" : score >= 700 ? "Very good" : score >= 650 ? "Good" : score >= 550 ? "Fair" : "Poor";
    return `<svg viewBox="0 0 200 120" width="230" role="img" aria-label="CredAI score ${score} of 900">
      <path d="M20 95 A80 80 0 0 1 180 95" fill="none" stroke="var(--line)" stroke-width="14" stroke-linecap="round"/>
      <path d="M20 95 A80 80 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}" fill="none" stroke="${color}" stroke-width="14" stroke-linecap="round"/>
      <text x="100" y="82" text-anchor="middle" font-size="34" font-weight="800" fill="var(--ink)">${score}</text>
      <text x="100" y="104" text-anchor="middle" font-size="12" fill="var(--muted)">${label} · out of 900</text>
      <text x="18" y="116" font-size="9" fill="var(--muted)">300</text><text x="170" y="116" font-size="9" fill="var(--muted)">900</text>
    </svg>`;
  }

  function donut(principal, interest) {
    const total = principal + interest, p = principal / total, C = 2 * Math.PI * 42;
    return `<svg class="doughnut" viewBox="0 0 100 100"><circle cx="50" cy="50" r="42" fill="none" stroke="var(--accent)" stroke-width="14"/>
      <circle cx="50" cy="50" r="42" fill="none" stroke="var(--brand)" stroke-width="14" stroke-dasharray="${(p * C).toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90 50 50)"/>
      <text x="50" y="54" text-anchor="middle" font-size="13" font-weight="800" fill="var(--ink)">${Math.round(p * 100)}%</text></svg>`;
  }

  function render(r) {
    const d = { ...r.decision }, risk = r.risk_assessment, fraud = r.fraud_assessment, a = r.applicant, prof = r.profile || {};
    const live = ["APPROVED", "PARTIALLY_APPROVED"].includes(r.final_decision);
    if (!live) d.offers = [];
    if (r.status === "REVIEWED") d.reasons = [`An underwriter set this application to “${(DECISION[r.final_decision] || {}).label || r.final_decision}”.` + (r.reviewer_note ? ` Note: ${r.reviewer_note}` : "")];
    const dec = DECISION[r.final_decision] || { label: r.final_decision, cls: "info" };
    const first = (a.full_name || "").split(" ")[0] || "there";
    const title = {
      APPROVED: `Congratulations ${esc(first)}, you're approved for ${lakh(d.approved_amount)}`,
      PARTIALLY_APPROVED: `${esc(first)}, you're approved for ${lakh(d.approved_amount)}`,
      MANUAL_REVIEW: `${esc(first)}, your application needs a quick manual check`,
      REJECTED: `Sorry ${esc(first)}, we can't approve this loan right now`,
    }[r.final_decision] || dec.label;
    const sub = {
      APPROVED: `For ${PURPOSE[a.loan_purpose] || "your needs"}` + (d.offers.length ? ` · rate from ${Math.min(...d.offers.map((o) => o.interest_rate))}% p.a.` : ""),
      PARTIALLY_APPROVED: `You asked for ${lakh(d.requested_amount)}. ${esc(d.reasons[0] || "")}`,
      MANUAL_REVIEW: "An underwriter will review it, usually within 4 working hours. No further action needed now.",
      REJECTED: esc(d.reasons.join(" ")),
    }[r.final_decision] || "";
    const accepted = (() => { try { return JSON.parse(localStorage.getItem("credai:accepted:" + r.application_id)); } catch { return null; } })();

    const reasonHtml = [
      ...d.reasons.map((x) => `<div class="reason ${dec.cls}">${esc(x)}</div>`),
      ...d.conditions.map((x) => `<div class="reason info">ℹ ${esc(x)}</div>`),
      ...(live || r.status !== "REVIEWED" ? d.positives : []).map((x) => `<div class="reason ok">✓ ${esc(x)}</div>`),
    ].join("");

    const maxImpact = Math.max(0.3, ...risk.factors.map((f) => Math.abs(f.impact)));
    const factorHtml = risk.factors.filter((f) => Math.abs(f.impact) >= 0.01).slice(0, 7).map((f) => {
      const w = Math.round((Math.abs(f.impact) / maxImpact) * 100);
      return `<div class="factor"><span>${esc(f.factor)}</span>
        <span class="lft">${f.impact < 0 ? `<i style="width:${w}%"></i>` : ""}</span>
        <span class="rgt">${f.impact > 0 ? `<i style="width:${w}%"></i>` : ""}</span></div>`;
    }).join("");

    const aff = d.affordability;
    const foirPct = Math.min(100, aff.foir_after_pct);
    const foirColor = aff.foir_after_pct <= 35 ? "var(--ok)" : aff.foir_after_pct <= 50 ? "var(--warn)" : "var(--bad)";

    qs("#root").innerHTML = `
    <section class="hero ${dec.cls}">
      <div class="row wrap" style="gap:8px"><span class="pill"><span class="dot" style="background:#fff"></span>${esc(dec.label)}</span>
        <span class="pill mono">${esc(r.application_id)}</span><span class="pill">${fmtDate(r.timestamp)}</span>
        ${r.status === "REVIEWED" ? '<span class="pill">Reviewed by underwriter</span>' : ""}</div>
      <h1>${title}</h1><p>${sub}</p>
      <div class="actions no-print">
        <a class="btn white" href="/api/applications/${encodeURIComponent(r.application_id)}/report.pdf">Download decision report (PDF)</a>
        <button class="btn ghost" onclick="window.print()">Print</button>
        <button class="btn ghost" id="copy-link">Copy link</button>
      </div>
    </section>

    <div class="layout">
      <div class="stack">
        ${d.offers.length ? `
        <div class="card" id="offers-card">
          <div class="card-title"><h3>Choose your offer</h3>${accepted ? `<span class="pill ok"><span class="dot"></span>Accepted ${esc(accepted.tier)}</span>` : ""}</div>
          <div class="grid g3" id="offers">${d.offers.map((o, i) => `
            <div class="offer ${o.recommended ? "sel" : ""}" data-i="${i}" tabindex="0" role="button" aria-pressed="${o.recommended}">
              ${o.recommended ? '<span class="pill brand rec">Recommended</span>' : ""}
              <div class="kicker">${esc(o.tier)}</div>
              <div class="emi">${inr(o.emi)}<span class="small muted" style="font-weight:500">/month</span></div>
              <div class="small muted">${lakh(o.amount)} · ${o.tenure_months} months · ${o.interest_rate}% p.a.</div>
              <div class="small" style="margin-top:6px">Total interest <b>${inr(o.total_interest)}</b></div>
            </div>`).join("")}</div>

          <div class="card flat" style="margin-top:16px;background:var(--surface-2)">
            <div class="row between wrap"><b>Customise</b><span class="small muted">Rate <b id="c-rate"></b> p.a. · reducing balance</span></div>
            <label class="field-label" style="margin-top:10px">Amount <b id="c-amt-l"></b></label>
            <input type="range" class="slider" id="c-amt" step="5000" />
            <label class="field-label" style="margin-top:8px">Tenure <b id="c-ten-l"></b></label>
            <input type="range" class="slider" id="c-ten" min="6" step="6" />
            <div class="row wrap" style="gap:18px;margin-top:12px">
              <div id="c-donut"></div>
              <dl class="kv" style="flex:1;min-width:220px">
                <dt>Monthly EMI</dt><dd id="c-emi" style="font-size:1.2rem"></dd>
                <dt><span style="color:var(--brand)">■</span> Principal</dt><dd id="c-p"></dd>
                <dt><span style="color:var(--accent)">■</span> Total interest</dt><dd id="c-i"></dd>
                <dt>Processing fee (1.5% + GST)</dt><dd id="c-f"></dd>
                <dt>Total you repay</dt><dd id="c-t"></dd>
                <dt>EMIs as share of income</dt><dd id="c-foir"></dd>
              </dl>
            </div>
            <div id="c-warn" class="reason warn hidden" style="margin-top:10px"></div>
            <button class="btn lg block no-print" id="btn-accept" style="margin-top:12px" ${r.final_decision === "MANUAL_REVIEW" ? "disabled" : ""}>Accept this offer</button>
          </div>
        </div>` : ""}

        <div class="card">
          <h3>Why we decided this</h3>
          ${reasonHtml}
          ${prof.summary ? `<p class="small muted" style="margin-top:10px">${esc(prof.summary)}</p>` : ""}
        </div>

        <div class="card">
          <div class="card-title"><h3>What shaped your score</h3><span class="small muted">From the model's own feature contributions</span></div>
          <div class="factor small muted" style="padding-bottom:2px"><span></span><span style="text-align:right;padding-right:8px">◀ lowers risk</span><span style="padding-left:8px">raises risk ▶</span></div>
          ${factorHtml}
          <p class="small muted" style="margin:10px 0 0">Gender never affects the decision: the model's output is averaged across genders. ${risk.bureau_data_used ? "Your CIBIL score was used." : "No CIBIL score was shared, so a cautious default was used."}</p>
        </div>

        <div class="card no-print">
          <div class="card-title"><h3>What-if: try a different amount</h3><span class="pill info">Live model</span></div>
          <p class="small muted">See how amount, tenure or closing an existing EMI changes your eligibility. This re-runs the same risk model — it doesn't change your application.</p>
          <div class="grid g3">
            <label class="field"><span class="field-label">Loan amount (₹)</span><input class="input" id="w-amt" type="number" min="10000" step="10000" value="${Math.round(a.loan_amount)}"></label>
            <label class="field"><span class="field-label">Tenure (months)</span><input class="input" id="w-ten" type="number" min="6" max="60" step="6" value="${a.loan_tenure_months}"></label>
            <label class="field"><span class="field-label">Existing EMIs (₹/month)</span><input class="input" id="w-emi" type="number" min="0" step="500" value="${Math.round(a.existing_emi || 0)}"></label>
          </div>
          <div class="sim-out" id="w-out"></div>
          <p class="small muted" style="margin:8px 0 0">* Indicative, before identity/fraud checks. Your actual decision is shown above.</p>
        </div>

        ${prof.improvement_tips && prof.improvement_tips.length ? `<div class="card"><h3>How to improve your chances</h3><ul style="margin:6px 0 0;padding-left:18px">${prof.improvement_tips.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
      </div>

      <aside class="stack">
        <div class="card score-wrap">
          <div class="kicker">CredAI score</div>
          ${gauge(risk.credit_score)}
          <div class="grid g2" style="width:100%;margin-top:8px">
            <div class="stat"><div class="v">${risk.probability_of_default}%</div><div class="l">Default probability</div></div>
            <div class="stat"><div class="v">${risk.risk_grade}</div><div class="l">Risk grade (A best)</div></div>
          </div>
        </div>
        <div class="card">
          <h3>Affordability</h3>
          <dl class="kv"><dt>Monthly income</dt><dd>${inr(aff.monthly_income)}</dd><dt>Existing EMIs</dt><dd>${inr(aff.existing_emi)}</dd>
          <dt>Max total EMI allowed</dt><dd>${inr(aff.max_total_emi)}</dd><dt>Max eligible loan</dt><dd>${inr(d.max_eligible_amount)}</dd></dl>
          <div class="row between small" style="margin-top:12px"><span>EMI burden after this loan</span><b>${aff.foir_after_pct}%</b></div>
          <div class="bar" style="margin-top:6px;position:relative"><i style="width:${foirPct}%;background:${foirColor}"></i></div>
          <div class="small muted" style="margin-top:4px">Limit ${aff.foir_limit_pct}% of income (RBI-style FOIR)</div>
        </div>
        <div class="card">
          <div class="card-title"><h3>Identity &amp; fraud checks</h3><span class="pill ${fraud.fraud_level === "CLEAN" || fraud.fraud_level === "LOW" ? "ok" : fraud.fraud_level === "MEDIUM" ? "warn" : "bad"}">${fraud.fraud_score}/100</span></div>
          <ul class="checks">${fraud.checks.map((c) => `<li class="${c.status}"><span class="ic">${{ pass: "✓", warn: "!", fail: "✕", skipped: "–" }[c.status]}</span><div><b>${esc(c.check)}</b><span class="small muted">${esc(c.detail)}</span></div></li>`).join("")}</ul>
        </div>
        <div class="card">
          <h3>Audit trail</h3>
          <ul class="timeline">${(r.audit_trail || []).map((e) => `<li><time>${fmtDate(e.t)}</time>${esc(e.event)}${e.note ? `<div class="small muted">${esc(e.note)}</div>` : ""}</li>`).join("")}</ul>
        </div>
      </aside>
    </div>`;

    qs("#copy-link").addEventListener("click", () => {
      navigator.clipboard?.writeText(location.href).then(() => toast("Link copied", "ok"), () => toast(location.href));
    });
    if (d.offers.length) initOffers(r);
    initWhatIf(r);
  }

  function initOffers(r) {
    const d = r.decision, aff = d.affordability;
    const amt = qs("#c-amt"), ten = qs("#c-ten");
    amt.min = 10000; amt.max = d.approved_amount;
    ten.max = Math.max(...d.offers.map((o) => o.tenure_months), d.tenure_months);
    let rate;
    function select(i) {
      const o = d.offers[i];
      qsa(".offer").forEach((el) => { el.classList.toggle("sel", +el.dataset.i === i); el.setAttribute("aria-pressed", String(+el.dataset.i === i)); });
      rate = o.interest_rate;
      amt.value = o.amount; ten.value = o.tenure_months;
      update();
    }
    function update() {
      const P = +amt.value, n = +ten.value, e = emi(P, rate, n), interest = e * n - P;
      const fee = Math.round(P * 0.015 * 1.18);
      const foir = ((aff.existing_emi + e) / aff.monthly_income) * 100;
      qs("#c-rate").textContent = rate + "%";
      qs("#c-amt-l").textContent = inr(P);
      qs("#c-ten-l").textContent = n + " months";
      qs("#c-emi").textContent = inr(e);
      qs("#c-p").textContent = inr(P);
      qs("#c-i").textContent = inr(interest);
      qs("#c-f").textContent = inr(fee);
      qs("#c-t").textContent = inr(e * n + fee);
      qs("#c-foir").textContent = foir.toFixed(1) + "%";
      qs("#c-donut").innerHTML = donut(P, Math.max(0, interest));
      const w = qs("#c-warn");
      const over = foir > aff.foir_limit_pct;
      w.classList.toggle("hidden", !over);
      w.textContent = over ? `At this tenure the EMI would take ${foir.toFixed(0)}% of your income — above our ${aff.foir_limit_pct}% limit. Choose a longer tenure or lower amount.` : "";
      const btn = qs("#btn-accept");
      if (r.final_decision !== "MANUAL_REVIEW") btn.disabled = over;
      btn.dataset.payload = JSON.stringify({ amount: P, tenure: n, rate, emi: Math.round(e), fee, total: Math.round(e * n + fee), tier: "Custom" });
    }
    qsa(".offer").forEach((el) => {
      el.addEventListener("click", () => select(+el.dataset.i));
      el.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && select(+el.dataset.i));
    });
    amt.addEventListener("input", update); ten.addEventListener("input", update);
    select(Math.max(0, d.offers.findIndex((o) => o.recommended)));

    const modal = qs("#accept-modal");
    qs("#btn-accept").addEventListener("click", () => {
      const p = JSON.parse(qs("#btn-accept").dataset.payload);
      qs("#accept-body").innerHTML = `<dl class="kv"><dt>Loan amount</dt><dd>${inr(p.amount)}</dd><dt>Rate</dt><dd>${p.rate}% p.a. (reducing)</dd>
        <dt>Tenure</dt><dd>${p.tenure} months</dd><dt>EMI</dt><dd>${inr(p.emi)}</dd><dt>Processing fee incl. GST</dt><dd>${inr(p.fee)}</dd><dt>Total cost</dt><dd>${inr(p.total)}</dd></dl>`;
      qs("#kfs-ok").checked = false; qs("#accept-confirm").disabled = true;
      modal.classList.remove("hidden");
    });
    qs("#kfs-ok").addEventListener("change", (e) => (qs("#accept-confirm").disabled = !e.target.checked));
    qs("#accept-cancel").addEventListener("click", () => modal.classList.add("hidden"));
    qs("#accept-confirm").addEventListener("click", () => {
      const p = JSON.parse(qs("#btn-accept").dataset.payload);
      p.at = new Date().toISOString();
      localStorage.setItem("credai:accepted:" + r.application_id, JSON.stringify(p));
      modal.classList.add("hidden");
      qs("#offers-card").insertAdjacentHTML("afterbegin", `<div class="reason ok" style="margin-bottom:14px"><b>Offer accepted.</b> Next steps: e-sign the loan agreement and set up auto-debit (e-NACH). In this demo, the flow ends here.</div>`);
      toast("Offer accepted", "ok");
    });
  }

  function initWhatIf(r) {
    const a = r.applicant;
    let timer;
    async function run() {
      const body = {
        monthly_income: a.monthly_income, loan_amount: +qs("#w-amt").value || 10000,
        loan_tenure_months: Math.min(60, Math.max(6, +qs("#w-ten").value || 24)),
        age_years: a.age_years, work_experience_years: a.work_experience_years || 0,
        existing_emi: +qs("#w-emi").value || 0, employment_type: a.employment_type,
        education: a.education, marital_status: a.marital_status, own_property: a.own_property,
        own_vehicle: a.own_vehicle, dependents: a.dependents || 0, cibil_score: a.cibil_score, city: a.city,
      };
      const out = qs("#w-out");
      try {
        const res = await api("/api/risk", { method: "POST", body });
        const dec = res.decision, DEC = DECISION[dec.decision] || { label: dec.decision, cls: "info" };
        out.innerHTML = `
          <div class="stat"><div class="l">Likely outcome*</div><div class="v" style="font-size:1.05rem"><span class="pill ${DEC.cls}"><span class="dot"></span>${DEC.label}</span></div></div>
          <div class="stat"><div class="l">EMI at ${dec.interest_rate}%</div><div class="v">${inr(dec.affordability.requested_emi)}</div></div>
          <div class="stat"><div class="l">Max you could get</div><div class="v">${lakh(dec.max_eligible_amount)}</div></div>`;
      } catch (e) {
        out.innerHTML = `<div class="reason warn" style="grid-column:1/-1">${esc(e.message)}</div>`;
      }
    }
    ["#w-amt", "#w-ten", "#w-emi"].forEach((s) => qs(s).addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 350); }));
    run();
  }

  async function boot() {
    if (!id) {
      qs("#root").innerHTML = `<div class="card" style="margin-top:30px;text-align:center"><h2>No application selected</h2><p class="muted">Start a new application to get a decision.</p><a class="btn" href="apply.html">Apply now</a></div>`;
      return;
    }
    let rec = null;
    try { rec = await api("/api/applications/" + encodeURIComponent(id)); }
    catch (e) {
      try { rec = JSON.parse(sessionStorage.getItem("credai:" + id)); } catch {}
      if (!rec) {
        qs("#root").innerHTML = `<div class="card" style="margin-top:30px;text-align:center"><h2>Couldn't load application</h2><p class="muted">${esc(e.message)}</p><a class="btn" href="apply.html">Start a new application</a></div>`;
        return;
      }
    }
    document.title = `${(DECISION[rec.final_decision] || {}).label || "Decision"} — CredAI`;
    render(rec);
  }
  boot();
})();
