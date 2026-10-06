"use strict";
const $ = (sel) => document.querySelector(sel);
const METRICS = ["QR", "N", "LR", "OT", "SN"];
const METRIC_LABEL = { QR: "Quick returns (<11 h rest)", N: "Night shifts", LR: "Long stretches (6+ days)", OT: "Overtime hours", SN: "Last-minute call-ins" };
const METRIC_TIP = {
  QR: "Quick return: back at work after less than 11 hours' rest between two shifts",
  N: "Number of night shifts worked in the planning window",
  LR: "Long stretch: 6 or more working days in a row",
  OT: "Overtime hours: hours worked above the nurse's contract",
  SN: "Last-minute call-in: a change a nurse has to absorb with little warning",
};
const TRADEOFF_WORD = { quick_returns: "quick returns", nights: "night shifts", long_runs: "long stretches", overtime: "overtime",
  short_notice: "last-minute call-ins", stability: "stability (few changes)", concentration: "load concentrated on a few nurses" };
const tradeoffWord = (t) => TRADEOFF_WORD[t] ?? String(t ?? "").replaceAll("_", " ");
const SHIFT_WORD = { D: "day", E: "evening", N: "night" };
const shiftWords = (s) => String(s ?? "").replace(/(^|: |→ |; )([DEN])\b/g, (_, p, c) => `${p}${SHIFT_WORD[c]} shift`);
const TODAY = "Today's software (ORTEC-style)";
const MODE_LABEL = { baseline: TODAY, ai: "GenAI chooses (experimental)", strain: "Rule ranks, GenAI explains", auto: "Auto (hospital rule)", "auto-ai": "GenAI-chooser autoplay (experimental)", "auto-strain": "Hospital rule autoplay", "auto-baseline": "Today's software autoplay", policy: "Policy" };
// Column/label for "our" side: the rule-ranked choice by default; GenAI only in the experimental arm.
const oursLabel = () => (mode === "ai" ? "GenAI chooses (experimental)" : "Rule-ranked choice");
const oursShort = () => (mode === "ai" ? "GenAI" : "the hospital rule");
const LOWER = ' <span class="metric-hint">(lower is better)</span>';
// Display backstop for the presenter view: no "Option_N" ids, no "Nurse_NN" ids anywhere.
const noOptionIds = (s) => String(s ?? "").replace(/\bOption_0*(\d+)\b/gi, (_, n) => { const d = descOf(`Option_${Number(n)}`); return d ? `“${d}”` : "another option"; });
const niceNurse = (s) => noOptionIds(String(s ?? "").replace(/Nurse_(\d+)/g, "Nurse $1"));
const MINUS = "\u2212";
const signedWord = (n) => (n > 0 ? `+${n}` : n < 0 ? `${MINUS}${-n}` : "0");
function factsBadge(verified, presenter) {
  if (presenter) return verified ? '<span class="badge ok">✓ Numbers checked against the roster</span>'
    : '<span class="badge bad">⚠️ Some numbers do not match the roster — check before applying</span>';
  return verified ? '<span class="badge ok">Facts checked ✅</span>' : '<span class="badge bad">Facts check found a problem ⚠️</span>';
}
const shortNotice = (h) => h < 48;
let autoRunning = false;
let autoMode = "strain";
let autoTimer = null;
let defaultMode = "strain";  // from policy.json "mode" (rule_explains -> strain, genai_chooser -> ai)
let mode = "strain";
let explanation = null;
let explainPending = false;
let explainError = null;
let state = null;
let options = [];
let decision = null;
let decisionError = null;
let chart = null;
let scoreChart = null;
let comparison = null;
let weights = null;
let policyForm = null;
let proposal = null;
let decisionPending = false;
let reqToken = 0;
let applying = false;
const UNAVAILABLE = "GenAI is unavailable right now — a backup choice is shown.";
const CHECK_NOTE = "Checks verify the numbers and wording against the roster data; the reasoning itself is reviewed by the planner.";
const staleReq = (tok, eid, m) => tok !== reqToken || mode !== m || !state || !state.event || state.event.event_id !== eid;
const isPresenter = () => document.body.classList.contains("presenter");
const RULE = "Hospital rule check";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || res.statusText));
  return body;
}

let toastTimer = null;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 4000);
}

async function guarded(fn) {
  try { await fn(); } catch (e) { toast(e.message); }
}

function focusNurses() {
  return new Set(options.flatMap((o) => (o.nurses ? o.nurses.map((n) => n.nurse) : [o.nurse])));
}

async function newScenario() {
  state = await api("/api/scenario", { method: "POST", body: JSON.stringify({ seed: Number($("#seed").value) || 0 }) });
  options = [];
  comparison = null;
  hideExplanation();
  render();
  await loadAudit();
}

async function fastForward(body) {
  const r = await api("/api/fast-forward", { method: "POST", body: JSON.stringify({ ...body, mode }) });
  state = r.state;
  toast(`Auto-resolved ${r.resolved} sick calls with ${mode === "baseline" ? "today's software" : RULE}`);
  await loadOptions();
  render();
  await loadAudit();
}

async function nextEvent() {
  const r = await api("/api/next-event", { method: "POST" });
  state = r.state;
  if (r.done) toast("All sick calls processed.");
  await loadOptions();
  render();
  await loadAudit();
}

async function loadOptions() {
  hideExplanation();
  if (!state || !state.event || state.event.unfilled || autoRunning) { options = []; comparison = null; return; }
  const r = await api(`/api/options?mode=${mode}`);
  options = r.options;
  comparison = r.comparison;
  if (mode === "strain") explain();
  if (mode === "ai") decide();
}

function hideExplanation() {
  $("#explain-card").classList.add("hidden");
  $("#decide-card").classList.add("hidden");
  decision = null;
  decisionError = null;
  decisionPending = false;
  explanation = null;
  explainPending = false;
  explainError = null;
  reqToken++;
}

function aiPickId() { return decision && decision.decision ? decision.decision.chosen_option : null; }
function formulaTopId() { const t = options.find((o) => o.rank === 1); return t ? t.id : null; }
const optName = (id) => String(id ?? "");
function descOf(id) {
  const o = options.find((x) => x.id === id);
  if (o && o.description) return o.description;
  const c = decision && decision.comparison;
  if (c && c.ours.id === id) return c.ours.description;
  if (c && c.ortec.id === id) return c.ortec.description;
  return null;
}

async function decide() {
  decisionPending = true;
  $("#decide-card").classList.remove("hidden");
  $("#decide-head").textContent = "GenAI is thinking…";
  $("#decide-head").title = ""; $("#decide-text").title = "";
  $("#decide-meta").textContent = "";
  $("#decide-text").textContent = ""; clearShowFull("#decide-text");
  $("#decide-issues").innerHTML = "";
  $("#decide-formula").textContent = "";
  const eid = state.event.event_id, tok = reqToken, m = mode;
  try {
    const r = await api("/api/decide", { method: "POST" });
    if (staleReq(tok, eid, m)) return;
    decision = r;
    decisionPending = false;
    renderDecision(r);
    renderOptions();
    renderCompare();
  } catch (e) {
    if (staleReq(tok, eid, m)) return;
    decisionError = e.message;
    decisionPending = false;
    $("#decide-head").textContent = isPresenter() ? UNAVAILABLE : `GenAI decision unavailable: ${e.message}`;
    $("#decide-head").title = e.message;
    renderCompare();
  }
}

// Show the short GenAI text; when it was cut, offer a link-style toggle for the full text.
function clearShowFull(id) {
  const n = $(id).nextElementSibling;
  if (n && n.classList.contains("show-full")) n.remove();
}

function setAiText(id, r, fallback) {
  const el = $(id);
  const nn = isPresenter() ? niceNurse : (x) => x;
  const full = nn(r.display_text ?? fallback);
  const short = nn(r.display_short ?? r.display_text ?? fallback);
  el.textContent = short;
  clearShowFull(id);
  if (!r.display_truncated || short === full) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "show-full linklike";
  btn.textContent = "Show full reasoning";
  let open = false;
  btn.addEventListener("click", () => {
    open = !open;
    el.textContent = open ? full : short;
    btn.textContent = open ? "Hide full reasoning" : "Show full reasoning";
  });
  el.insertAdjacentElement("afterend", btn);
}

function renderDecision(r) {
  const c = r.check;
  $("#decide-meta").textContent = "";
  $("#decide-formula").textContent = "";
  if (!r.decision) {
    $("#decide-head").textContent = isPresenter() ? UNAVAILABLE : "GenAI decision unavailable — use the hospital rule's pick or decide manually.";
    $("#decide-head").title = r.error || "";
    clearShowFull("#decide-text");
    $("#decide-text").textContent = isPresenter() ? "" : (r.error || "");
    $("#decide-text").title = r.error || "";
    $("#decide-issues").innerHTML = "";
    $("#decide-meta").innerHTML = `<span class="src">${esc(r.source)} · ${r.latency_ms} ms</span>`;
    return;
  }
  const d = r.decision;
  const badge = factsBadge(c.verified, isPresenter());
  const desc = descOf(d.chosen_option);
  $("#decide-head").innerHTML = isPresenter() ? `GenAI's choice: ${esc(niceNurse(desc ?? "see the comparison"))} ${badge}`
    : `GenAI chose ${esc(optName(d.chosen_option))}${desc ? ` (${esc(desc)})` : ""} ${badge}`;
  setAiText("#decide-text", r, d.reasoning);
  const issues = [];
  if (c.claims_false) issues.push(`${c.claims_false} of ${c.claims_total} numbers quoted by GenAI do not match the data`);
  if (c.unsupported_numbers.length) issues.push(`GenAI used numbers that are not in the data: ${c.unsupported_numbers.join(", ")}`);
  if (c.no_claims) issues.push("GenAI did not back its text with any numbers");
  if (c.direction_errors && c.direction_errors.length) issues.push(`GenAI wording says the opposite of the numbers (up vs down): ${c.direction_errors.join(", ")}`);
  $("#decide-issues").innerHTML = (isPresenter() ? "" : `<li>Main trade-off: ${esc(tradeoffWord(d.main_tradeoff))}</li>`) +
    issues.map((i) => `<li class="warn">${esc(i)}</li>`).join("") +
    (isPresenter() ? `<li class="muted">${esc(CHECK_NOTE)}</li>` : "");
  $("#decide-formula").innerHTML = `${RULE} top: ${esc(optName(r.formula_top))} — ` +
    (r.agrees ? "agrees ✅" : "differs ⚠️");
  $("#decide-meta").innerHTML = `<span class="src">${esc(r.source)} · ${r.latency_ms} ms</span>`;
}

// GenAI explains the rule's choice. The choice is already made: accept is enabled before this returns,
// and if GenAI fails the ranked table stays without a narrative (the server logs the failure at apply).
const EXPLAIN_UNAVAILABLE = "GenAI explanation unavailable — the rule's choice stands; see the ranked table.";
async function explain() {
  explainPending = true;
  $("#explain-card").classList.remove("hidden");
  clearShowFull("#explain-text");
  $("#explain-text").textContent = "GenAI is writing an explanation…";
  $("#explain-meta").textContent = "";
  $("#explain-claims").innerHTML = "";
  const eid = state.event.event_id, tok = reqToken, m = mode;
  try {
    const r = await api("/api/explain", { method: "POST" });
    if (staleReq(tok, eid, m)) return;
    explanation = r;
    explainPending = false;
    renderExplanation(r);
  } catch (e) {
    if (staleReq(tok, eid, m)) return;
    explainError = e.message;
    explainPending = false;
    clearShowFull("#explain-text");
    $("#explain-text").textContent = `${EXPLAIN_UNAVAILABLE} (${e.message})`;
  }
  renderCompare();
}

function explanationIssues(c) {
  const issues = [];
  if (c.claims_false) issues.push(`${c.claims_false} of ${c.claims_total} numbers quoted by GenAI do not match the data`);
  if (c.unsupported_numbers.length) issues.push(`GenAI used numbers that are not in the data: ${c.unsupported_numbers.join(", ")}`);
  const dir = (c.direction_errors || []).concat(c.nurse_direction_errors || []);
  if (dir.length) issues.push(`GenAI wording says the opposite of the numbers (up vs down): ${dir.join(", ")}`);
  return issues;
}

function renderExplanation(r) {
  const c = r.check;
  if (!r.explanation) {
    $("#explain-meta").innerHTML = `<span class="src">${esc(r.source)} · ${r.latency_ms} ms</span>`;
    clearShowFull("#explain-text");
    $("#explain-text").textContent = EXPLAIN_UNAVAILABLE + (r.error ? ` (${r.error})` : "");
    $("#explain-claims").innerHTML = "";
    return;
  }
  const badge = factsBadge(c.verified, isPresenter());
  $("#explain-meta").innerHTML = `${badge} <span class="src">${esc(r.source)} · ${r.latency_ms} ms</span>`;
  setAiText("#explain-text", r, r.explanation.text);
  $("#explain-claims").innerHTML = explanationIssues(c).map((i) => `<li class="warn">${esc(i)}</li>`).join("");
}

function askReason(pickFrom = null) {
  return new Promise((resolve) => {
    const dlg = $("#override-dlg");
    dlg.returnValue = "";
    $("#override-opt-wrap").classList.toggle("hidden", !pickFrom);
    if (pickFrom) $("#override-opt").innerHTML = pickFrom.map((o) =>
      `<option value="${esc(o.id)}">#${o.rank}: ${esc(niceNurse(o.description))}</option>`).join("");
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"
      ? { reason: $("#override-reason").value, option: pickFrom ? $("#override-opt").value : null } : null), { once: true });
    dlg.showModal();
  });
}

async function applyOption(opt, givenReason = null) {
  if (applying) return;
  let reason = givenReason;
  const needsReason = mode === "ai" && aiPickId() ? opt.id !== aiPickId() : opt.rank !== 1;
  if (needsReason && !reason) {
    const a = await askReason();
    if (!a) return;
    reason = a.reason;
  }
  applying = true;
  setApplyDisabled(true);
  let r;
  try {
    r = await api("/api/apply", { method: "POST", body: JSON.stringify({ option_id: opt.id, event_id: state.event.event_id, mode, override_reason: reason }) });
  } finally {
    applying = false;
    setApplyDisabled(false);
  }
  state = r.state;
  options = [];
  comparison = null;
  hideExplanation();
  render();
  await loadAudit();
}

function setApplyDisabled(d) {
  document.querySelectorAll("#options button[data-opt]").forEach((b) => { b.disabled = d || autoRunning; });
  if (d) $("#btn-apply-main").disabled = true; else renderApplyMain();
}

// Override from the presenter view: pick another ranked option and give a short reason.
async function overrideMain() {
  const top = mode === "ai" && aiPickId() ? aiPickId() : formulaTopId();
  const others = options.filter((o) => o.id !== top);
  if (!others.length) { toast("There is no other option for this sick call."); return; }
  const a = await askReason(others);
  if (!a) return;
  const opt = options.find((o) => o.id === a.option);
  if (opt) await applyOption(opt, a.reason);
}

async function applyMain() {
  const id = (mode === "ai" ? aiPickId() : null) || formulaTopId();
  const opt = options.find((o) => o.id === id);
  if (!opt) { toast("GenAI's pick is not among the current options — refresh with Next sick call."); return; }
  await applyOption(opt);
}

function renderApplyMain() {
  const btn = $("#btn-apply-main"), st = $("#apply-status");
  if (!btn) return;
  $("#btn-override-main").disabled = applying || autoRunning || options.length < 2 || mode === "baseline";
  if (mode !== "ai") {  // rule-ranked: accept is available at once; GenAI's explanation never gates it
    btn.textContent = "✓ Accept the rule's choice";
    btn.disabled = applying || autoRunning || !options.length || mode === "baseline";
    if (explainPending) st.innerHTML = '<span class="spinner"></span>GenAI is writing an explanation…';
    else st.textContent = "";
    return;
  }
  const unavailable = !!decisionError || (decision && !decision.decision);
  const ready = !!aiPickId();
  btn.textContent = unavailable ? (isPresenter() ? "Apply backup choice" : "Apply hospital rule's choice") : "Apply GenAI's choice (experimental)";
  btn.disabled = applying || autoRunning || !options.length || mode !== "ai" || !(ready || unavailable);
  if (decisionPending && !decision && !decisionError) st.innerHTML = '<span class="spinner"></span>GenAI is thinking…';
  else st.textContent = unavailable ? (isPresenter() ? UNAVAILABLE : "GenAI could not decide this one — the hospital rule check's pick is used.") : "";
}

async function setMode(m) {
  mode = m;
  document.querySelectorAll(".mode").forEach((b) => b.classList.toggle("active", b.dataset.mode === m));
  $("#policy-card").classList.toggle("hidden", m === "baseline");
  $("#btn-autoplay").textContent = `Let ${WHO[m]} handle the next`;
  $("#auto-step-title").textContent = `Let ${WHO[m]} handle the next sick calls`;
  $("#opts-title").textContent = m === "baseline" ? "Options (today's software order)" : "Ranked options (hospital rule)";
  $("#auto-ctl-tail").textContent = "sick calls";
  if (state) { await loadOptions(); render(); }
}

function storedView() {
  try { return localStorage.getItem("roster-view") === "expert" ? "expert" : "presenter"; } catch (e) { return "presenter"; }
}

async function setView(v) {
  document.body.classList.toggle("presenter", v === "presenter");
  document.body.classList.toggle("expert", v === "expert");
  $("#btn-view").textContent = v === "presenter" ? "Show details" : "Presenter view";
  try { localStorage.setItem("roster-view", v); } catch (e) { /* storage unavailable */ }
  if (v === "presenter" && mode === "baseline") await setMode(defaultMode);
  else if (state) render();
  if (decision && !decisionPending && !$("#decide-card").classList.contains("hidden")) renderDecision(decision);
}

async function startPresenter() {
  setPage("one");
  $("#btn-start").disabled = true;
  try { await startPresenterInner(); } finally { $("#btn-start").disabled = autoRunning; }
}

async function startPresenterInner() {
  const seed = Number($("#ward-sel").value) || 0;
  const week = Number($("#start-week").value) || 1;
  $("#seed").value = seed;
  state = await api("/api/scenario", { method: "POST", body: JSON.stringify({ seed }) });
  options = []; comparison = null;
  hideExplanation();
  render();
  if (week > 1) {
    const r = await api("/api/fast-forward", { method: "POST", body: JSON.stringify({ to_day: (week - 1) * 7 + 1, mode: "baseline", reset_history: true }) });
    state = r.state;
  }
  if (!state.event) state = (await api("/api/next-event", { method: "POST" })).state;
  await loadOptions();
  render();
  await loadAudit();
}

function render() { renderPreview(); renderEvent(); renderCompare(); renderOptions(); renderLegend(); renderGrid(); renderStrain(); renderScoreboard(); }

const SHIFT_ICON = { D: "☀️", E: "🌆", N: "🌙" };
const SHIFT_TIME = { D: "07:30–16:00", E: "15:30–23:00", N: "23:00–07:30" };
function sickHero(ev, sh) {
  const shiftName = `${sh.charAt(0).toUpperCase()}${sh.slice(1)} shift`;
  const total = state && state.days ? ` of ${state.days}` : "";
  const notice = shortNotice(ev.notice_h) ? `<span class="chip warn">⏰ Only ${Math.round(ev.notice_h)} h notice</span>` : "";
  const tail = ev.unfilled ? '<div class="sick-q warn">No one can legally take this shift — it runs short.</div>'
    : '<div class="sick-q">Someone has to cover this shift. Who should it be?</div>';
  return `<div class="sick-hero"><div class="sick-icon">🤒</div><div class="sick-body">` +
    `<div class="sick-who"><b>${esc(niceNurse(ev.absent))}</b> called in sick</div>` +
    `<div class="chips"><span class="chip">${SHIFT_ICON[ev.shift] ?? ""} ${esc(shiftName)} · ${SHIFT_TIME[ev.shift] ?? ""}</span>` +
    `<span class="chip">📅 Day ${ev.day + 1}${total}</span>${notice}</div>${tail}</div></div>`;
}

function renderEvent() {
  $("#remaining").textContent = state ? `${state.remaining_events} sick calls left · ${state.unfilled.length} unfilled` : "";
  const ev = state && state.event;
  const el = $("#event");
  $("#btn-next").classList.toggle("hidden", !state || (!!ev && !ev.unfilled) || autoRunning);
  if (!ev) { el.textContent = autoRunning ? "GenAI is working through the sick calls…" : state ? "No open sick call. Press “Next sick call”." : "Pick a ward and press ▶ Start."; return; }
  const sh = SHIFT_WORD[ev.shift] ?? ev.shift;
  if (isPresenter()) { el.innerHTML = sickHero(ev, sh); return; }
  el.innerHTML = `<b>${esc(ev.absent)}</b> called in sick — <b>${sh.charAt(0).toUpperCase()}${sh.slice(1)} shift</b>, day <b>${ev.day + 1}</b>` +
    (shortNotice(ev.notice_h) ? " — called in sick at short notice" : "") +
    (ev.unfilled ? '<div class="warn">No feasible repair option — the shift runs short.</div>' : "");
}

// Lower is better for every metric shown; ties stay neutral.
function cmpClass(a, b) { return a === b ? ["", ""] : a < b ? ["better", ""] : ["", "better"]; }

// Highlight the minimum among the available values; if all are equal nothing is highlighted.
function bestClasses(vals) {
  const present = vals.filter((v) => v !== null && v !== undefined);
  const min = Math.min(...present);
  const allSame = present.every((v) => v === min);
  return vals.map((v) => (!allSame && v === min ? "better" : ""));
}

function renderPreview() {
  const el = $("#preview");
  if (!state || !state.preview || isPresenter()) { el.innerHTML = ""; return; }
  const b = state.preview.baseline, s = state.preview.strain, a = state.preview.ai || null;
  const fix = (m) => (m ? Number(m.changes_per_repair.toFixed(2)) : null);
  const pv = isPresenter();
  const rows = [
    ["Nurses with 3+ quick returns in 4 weeks", "nurses_qr_ge3_28d", true],
    ["Quick returns in total", "QR_total", true],
    ["Most quick returns on one nurse", "max_qr"],
    ["Unfilled shifts", "unfilled", true],
    ["Last-minute call-ins", "SN_total"],
    ["Changes per repair", "changes_per_repair"],
  ].filter((r) => !pv || r[2]);
  const val = (m, k) => (m ? (k === "changes_per_repair" ? fix(m) : m[k]) : null);
  const cols = [0, 1, 2].filter((i) => (i !== 1 || a) && !(pv && i === 2));
  const headCells = [`<th>${TODAY}</th>`, "<th>GenAI chooses (experimental, measured)</th>", `<th>${RULE}</th>`];
  const thead = "<tr><th></th>" + cols.map((i) => headCells[i]).join("") + "</tr>";
  const body = rows.map(([l, k]) => {
    const vals = [val(b, k), val(a, k), val(s, k)];
    const cls = bestClasses(pv ? [vals[0], vals[1]].concat([null]) : vals);
    const cells = cols.map((i) => `<td class="${cls[i]}">${vals[i]}</td>`).join("");
    return `<tr><td>${l}${LOWER}</td>${cells}</tr>`;
  }).join("");
  const unf = (a ? [b.unfilled, a.unfilled] : [b.unfilled]).concat(pv ? [] : [s.unfilled]);
  const note = unf.every((u) => u === unf[0]) ? "Same coverage — the difference is who carries the load."
    : `Coverage (unfilled shifts): today's software ${b.unfilled}${a ? ` · GenAI chooses ${a.unfilled}` : ""}${pv ? "" : ` · hospital rule check ${s.unfilled}`}`;
  const missing = a ? "" : '<p class="muted-note">GenAI-chooser column: not measured for this seed (measured for seeds 0–4).</p>';
  el.innerHTML = `<table class="cmp">${thead}${body}</table><p class="banner-note">${note}</p>${missing}`;
}

function compareRows(r, o, thead) {
  const qr = (v) => (v < 0 ? `removes ${-v}` : String(v));
  const mv = (m) => (m ? `${esc(m.nurse)}: tiredness score ${m.before} → ${m.after}` : "nobody");
  const row = (label, fr, fo) => `<tr><td>${label}</td><td>${fr}</td><td>${fo}</td></tr>`;
  if (!o) {
    return `<table class="cmp">${thead}` + row("Option", esc(optName(r.id)), '<span class="muted">GenAI is thinking…</span>') +
      row("Change", esc(shiftWords(r.change_text)), "") + "</table>";
  }
  return `<table class="cmp">${thead}` +
    row("Option", esc(optName(r.id)), esc(optName(o.id))) +
    row("Change", esc(shiftWords(r.change_text)), esc(shiftWords(o.change_text))) +
    row("What happens", esc(r.description), esc(o.description)) +
    row(`New quick returns${LOWER}`, qr(r.new_quick_returns), qr(o.new_quick_returns)) +
    row("Who gets extra work", mv(r.extra_work), mv(o.extra_work)) +
    row("Who gets relief", mv(r.relief), mv(o.relief)) +
    row(`People disturbed${LOWER}`, r.people_disturbed, o.people_disturbed) + "</table>";
}

function cardHtml(title, lines, rest, cls, tag, how) {
  const [act, ...others] = lines;
  const restHtml = (rest || []).map((l) => `<p class="rest ${l.includes("⚠️") ? "bad" : "good"}">${esc(niceNurse(l))}</p>`).join("");
  const tagHtml = tag && isPresenter() ? `<span class="ctag">${esc(tag)}</span>` : "";
  const howHtml = how && isPresenter() ? `<p class="how">${esc(how)}</p>` : "";
  return `<div class="choice ${cls}"><h3>${esc(title)}${tagHtml}</h3>${howHtml}<p class="act">${esc(niceNurse(act))}</p>${restHtml}` +
    others.map((l) => `<p class="${l.startsWith("Cost") ? "cost" : ""}">${esc(niceNurse(l))}</p>`).join("") + "</div>";
}

// Presenter view: two side-by-side choice cards built from the server's deterministic card_lines.
function explainBubble() {
  if (explainPending) return '<div class="bubble"><div class="lbl">✨ GenAI explains the rule\'s choice</div><p class="muted"><span class="spinner"></span>GenAI is writing an explanation… (you can already accept)</p></div>';
  const r = explanation;
  if (explainError || (r && !r.explanation)) return `<div class="bubble"><div class="lbl">✨ GenAI explanation</div><p class="muted">${esc(EXPLAIN_UNAVAILABLE)}</p></div>`;
  if (!r) return "";
  const text = niceNurse(r.display_text ?? r.explanation.text);
  return `<div class="bubble"><div class="lbl">✨ GenAI explains the rule's choice</div><p>${esc(text)}</p>${factsBadge(r.check.verified, true)}</div>`;
}

function renderRuleCards() {
  const lines = comparison.card_lines;
  const rest = (lines && lines.rest_lines) || comparison.rest_lines || {};
  const ORTEC_HOW = "Looks for: free contract hours and the fewest shift changes. Does not look at how tired anyone is.";
  const RULE_HOW = "Ranks every legal option with the hospital's fairness formula: rest, nights, overtime and last-minute calls over 8 weeks.";
  const ortec = cardHtml("🖥️ Today's software", lines ? lines.ortec : [comparison.ortec.description], rest.ortec, "ortec", "Simplest fix", ORTEC_HOW);
  const same = comparison.ours.id === comparison.ortec.id;
  const ours = cardHtml("⚖️ Hospital rule's choice", lines ? lines.ours : [comparison.ours.description], rest.ours, "genai",
    same ? "Ranked #1 · same as today's software" : "Ranked #1", RULE_HOW);
  const diffText = niceNurse(comparison.difference || comparison.who_words || "");
  const diff = diffText ? `<div class="diff"><span class="diff-lbl">👉 The difference</span>${esc(diffText)}</div>` : "";
  $("#compare").innerHTML = `<div class="choice-cards vs-cards">${ortec}<div class="vs">vs</div>${ours}</div>${diff}`;
  $("#genai-explains").innerHTML = explainBubble();
}

function renderCards(c, backup = false) {
  const lines = (c && c.card_lines) || comparison.card_lines;
  const rest = (lines && lines.rest_lines) || (comparison && comparison.rest_lines) || {};
  const ORTEC_T = "🖥️ Today's software", GENAI_T = "✨ GenAI chooses (experimental)";
  const ORTEC_HOW = "Looks for: free contract hours and the fewest shift changes. Does not look at how tired anyone is.";
  const GENAI_HOW = "Looks at: every nurse's rest, nights, overtime and last-minute calls over 8 weeks, then picks the fairest fix.";
  const ortec = cardHtml(ORTEC_T, lines ? lines.ortec : [comparison.ortec.description], rest.ortec, "ortec", "Simplest fix", ORTEC_HOW);
  const genai = backup ? cardHtml("🛟 Backup choice", lines.ours, rest.ours, "genai backup", "GenAI unavailable",
      "GenAI did not answer in time, so the hospital's fairness rule picked this fix.")
    : c && c.card_lines ? cardHtml(GENAI_T, c.card_lines.ours, (c.card_lines.rest_lines || {}).ours, "genai", "GenAI's pick", GENAI_HOW)
    : `<div class="choice genai"><h3>${GENAI_T}</h3><p class="how">${esc(GENAI_HOW)}</p><p class="muted thinking"><span class="spinner"></span>GenAI is reading the roster and thinking…</p></div>`;
  const diffText = c ? niceNurse(c.difference || c.who_words || "") : "";
  const diff = diffText ? `<div class="diff"><span class="diff-lbl">👉 The difference</span>${esc(diffText)}</div>` : "";
  $("#compare").innerHTML = `<div class="choice-cards vs-cards">${ortec}<div class="vs">vs</div>${genai}</div>${diff}`;
  const ex = $("#genai-explains");
  if (decision && decision.decision) {
    // The option text is already on the GenAI card; start the explanation with "This choice" instead of repeating it.
    const short = niceNurse(decision.display_text ?? decision.decision.reasoning).replace(/^“[^”]+”/, "This choice");
    const badge = decision.check ? factsBadge(decision.check.verified, true) : "";
    ex.innerHTML = `<div class="bubble"><div class="lbl">✨ GenAI explains its choice</div><p>${esc(short)}</p>${badge}</div>`;
  } else ex.innerHTML = "";
}

function renderCompare() {
  const card = $("#compare-card");
  renderApplyMain();
  $("#rule-line").textContent = "";
  if (!comparison || !options.length) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  const words = (c) => (isPresenter() ? niceNurse(c.who_words ?? c.plain_words) : c.plain_words);
  if (mode === "ai") {
    if (isPresenter()) $("#compare-title").innerHTML = '<span class="step"><span class="num">2</span>Two ways to fill the gap</span>';
    else $("#compare-title").textContent = "This decision: Today's software vs GenAI chooses (experimental)";
    const thead = isPresenter() ? "<tr><th></th><th>Today's software</th><th>GenAI chooses</th></tr>"
      : "<tr><th></th><th>Today's software would…</th><th>GenAI chooses (experimental)</th></tr>";
    const c = decision && decision.comparison ? decision.comparison : null;
    const failed = decisionError || (decision && !decision.decision);
    if (failed && isPresenter() && comparison.card_lines) { renderCards(null, true); return; }
    if (failed || (decision && !c)) {
      const why = decisionError || (decision && decision.error) || "";
      $("#compare").innerHTML = decision && decision.decision
        ? "<p class=\"muted\">GenAI chose an option, but the comparison is missing.</p>"
        : `<p class="muted"></p>`;
      if (!(decision && decision.decision)) $("#compare p").textContent = isPresenter() ? UNAVAILABLE : "GenAI decision unavailable" + (why ? `: ${why}` : "") + " — use the hospital rule's pick or decide manually.";
      $("#plain-text").textContent = "";
      $("#genai-explains").innerHTML = "";
      return;
    }
    if (isPresenter()) { renderCards(c); return; }
    $("#compare").innerHTML = compareRows(comparison.ortec, c ? c.ours : null, thead);
    if (c) $("#rule-line").textContent = `${RULE}: ` + (c.formula_top === c.ours.id ? "agrees ✅" : `prefers ${optName(c.formula_top)} ⚠️`);
    $("#plain-text").textContent = c ? words(c) : "";
    return;
  }
  if (mode === "strain" && isPresenter()) {
    $("#compare-title").innerHTML = '<span class="step"><span class="num">2</span>Two ways to fill the gap — the rule ranks, you decide</span>';
    renderRuleCards();
    return;
  }
  $("#compare-title").textContent = "This decision: Today's software vs hospital rule";
  const col = mode === "strain" ? `${RULE} ranks #1…` : `${RULE} would…`;
  $("#compare").innerHTML = compareRows(comparison.ortec, comparison.ours,
    `<tr><th></th><th>Today's software would…</th><th>${col}</th></tr>`);
  $("#plain-text").textContent = words(comparison);
  $("#genai-explains").innerHTML = "";
}

function renderLegend() {
  const w = weights;
  $("#legend").textContent = w && options.length
    ? `Tiredness score = ${w.QR} points per quick return, ${w.N} per night shift, ${w.LR} per long stretch of 6+ days, ${w.OT} per overtime hour, ${w.SN} per last-minute call-in (set by the hospital). Higher = more worn out.`
    : "";
}

function countersHtml(st) {
  const o = st.ours, r = st.ortec;
  const qr = (label, v) => `<div class="side"><span class="who">${label}</span><span class="big ${v < 0 ? "win" : v > 0 ? "bad" : ""}">${esc(signedWord(v))}</span></div>`;
  const cost = (label, val) => `<div class="side"><span class="who">${label}</span><span class="big">${esc(signedWord(val))}</span></div>`;
  return `<div class="counters">
    <div class="counter benefit"><div class="kind">The benefit</div><div class="what">Short rests between shifts (under 11 h)</div><div class="pair">${qr("Today's software", r.quick_returns_change)}${qr(oursLabel(), o.quick_returns_change)}</div><div class="cap">Change on the roster since ${oursShort()} took over — fewer is better</div></div>
    <div class="counter price"><div class="kind">The price</div><div class="what">Extra last-minute calls to nurses</div><div class="pair">${cost("Today's software", r.extra_late_calls)}${cost(oursLabel(), o.extra_late_calls)}</div><div class="cap">Nurses asked to change their plans at short notice</div></div></div>`;
}

function renderScoreboard() {
  if (!state || !state.scoreboard) return;
  const { ours, ortec, history, start } = state.scoreboard;
  const st = state.since_takeover;
  const pres = isPresenter();
  const tr = $("#tradeoff");
  let more;
  if (pres && st) {
    const n = st.calls_handled;
    $("#score-title").innerHTML = `<span class="step"><span class="num">4</span>Score so far</span> <span class="score-sub">${n} sick call${n === 1 ? "" : "s"} handled — same sick calls for both</span>`;
    $("#scoreboard").innerHTML = n ? countersHtml(st)
      : `<p class="score-empty">Accept a choice or let ${oursShort()} handle the next sick calls — the score starts counting here.</p>`;
    more = st.ours.extra_late_calls > st.ortec.extra_late_calls;
  } else {
    $("#score-title").textContent = `This ward since ${oursShort()} took over`;
    const rows = [["Quick returns", "quick_returns", true], ["Nurses with 3+ quick returns in 4 weeks", "nurses_qr_ge3_28d", true],
      ["Highest nurse tiredness score", "max_load"], ["Last-minute call-ins", "short_notice_calls", true], ["Shifts changed", "shifts_changed"]];
    $("#scoreboard").innerHTML = `<table class="cmp"><tr><th></th><th>Today's software</th><th>${oursLabel()}</th></tr>` +
      rows.map(([l, k]) => { const [cx, cy] = cmpClass(ortec[k], ours[k]);
        return `<tr><td>${l}${LOWER}</td><td class="${cx}">${ortec[k]}</td><td class="${cy}">${ours[k]}</td></tr>`; }).join("") + "</table>";
    const diff = ortec.quick_returns - ours.quick_returns;
    const who = oursLabel();
    $("#score-note").textContent = !history.length ? "" : diff > 0 ? `${who}: −${diff} quick returns vs today's software so far`
      : diff < 0 ? `${who}: +${-diff} quick returns vs today's software so far` : `${who}: same number of quick returns as today's software so far`;
    more = ours.short_notice_calls > ortec.short_notice_calls;
  }
  tr.classList.toggle("hidden", !more);
  tr.textContent = more ? `⚖️ The trade-off: ${oursShort()} makes a few more phone calls to spare tired nurses from short rests.` : "";
  if (!window.Chart || pres) return;
  const labels = [0, ...history.map((h) => h.n)];
  const first = start ? start.qr : null;
  const datasets = [
    { label: "Today's software", data: [first, ...history.map((h) => h.ortec_qr)], borderColor: "#9ca3af", backgroundColor: "#9ca3af", pointRadius: 0, tension: 0.2 },
    { label: oursLabel(), data: [first, ...history.map((h) => h.ours_qr)], borderColor: "#1f6feb", backgroundColor: "#1f6feb", pointRadius: 0, tension: 0.2 }];
  const data = { labels, datasets };
  if (scoreChart) { scoreChart.data = data; scoreChart.update(); return; }
  scoreChart = new Chart($("#score-chart"), { type: "line", data, options: { animation: false, maintainAspectRatio: false,
    plugins: { title: { display: true, text: "Quick returns after each sick call (lower is better)" }, legend: { position: "bottom" } },
    scales: { x: { title: { display: true, text: "Sick calls handled" } }, y: {} } } });
}

function applyBtn(o) {
  const dis = autoRunning ? " disabled" : "";
  if (mode === "ai") {
    const pick = aiPickId() ? o.id === aiPickId() : o.rank === 1;
    return `<button${dis} data-opt="${esc(o.id)}" class="${pick ? "primary" : ""}">${pick ? (aiPickId() ? "Apply (GenAI pick)" : "Apply (top)") : "Apply"}</button>`;
  }
  return `<button${dis} data-opt="${esc(o.id)}" class="${o.rank === 1 ? "primary" : ""}">${o.rank === 1 ? "Apply (top)" : "Apply"}</button>`;
}

function metricCell(n, m) {
  const b = n.before[m];
  const a = n.after[m];
  return `<span class="${a > b ? "up" : ""}">${esc(n.nurse)}: ${b} → ${a}</span>`;
}

// Presenter: a compact ranked table (top 5) — rule rank, what happens, load change, today's-software rank.
function renderOptionsCompact(el) {
  const ortecTop = options.find((o) => o.rank_baseline === 1);
  const rows = options.slice(0, 5).map((o) => {
    const tags = (o.rank === 1 ? '<span class="tag formula">Rule\'s choice</span>' : "") +
      (o.rank_baseline === 1 ? '<span class="tag">Today\'s software</span>' : "");
    return `<tr class="${o.rank === 1 ? "top" : ""}"><td>${o.rank}</td><td>${esc(niceNurse(o.description))}${tags}</td>` +
      `<td>${o.n_changes}</td><td>${signedWord(Number(o.delta_strain.toFixed(1)))}</td><td>${o.rank_baseline}</td></tr>`;
  }).join("");
  const more = options.length > 5 ? `<p class="muted">+ ${options.length - 5} more legal options${ortecTop && ortecTop.rank > 5 ? ` (today's software's pick is ranked #${ortecTop.rank})` : ""}.</p>` : "";
  el.innerHTML = `<table class="opts"><tr><th>Rule rank</th><th>What happens</th><th>Shifts changed</th>` +
    `<th title="Change in the combined tiredness score of the nurses involved">Load change</th><th>Today's software rank</th></tr>${rows}</table>${more}`;
}

function renderOptions() {
  const el = $("#options");
  if (!options.length) { el.innerHTML = ""; return; }
  if (isPresenter() && mode !== "baseline") { renderOptionsCompact(el); return; }
  const RANK_TIP = "Rank by the hospital rule check (tiredness score; 1 = recommended)";
  const ORTEC_TIP = "Rank by today's software: fewest changes, then contract fit";
  const head = mode === "baseline"
    ? `<tr><th>Option</th><th title="${ORTEC_TIP}">Today's software rank</th><th>Change</th><th>What happens</th><th>Nurse</th><th>Contract hours per week</th><th>Hours this period</th><th>Changes</th><th></th></tr>`
    : `<tr><th>Option</th><th title="${RANK_TIP}">Rule rank</th><th title="${ORTEC_TIP}">Today's software rank</th><th>Change</th><th>What happens</th>` + METRICS.map((m) => `<th title="${esc(METRIC_TIP[m])}">${esc(METRIC_LABEL[m])}</th>`).join("") + `<th title="How much this option changes the combined tiredness score of the nurses involved">Change in tiredness</th><th></th></tr>`;
  const pickId = mode === "ai" ? aiPickId() : null;
  const topId = mode === "ai" ? formulaTopId() : null;
  const tags = (o) => (o.id === pickId ? '<span class="tag">GenAI pick</span>' : "") +
    (o.id === topId ? `<span class="tag formula">${RULE}</span>` : "");
  const rowCls = (o) => (mode === "ai" ? (o.id === pickId ? "ai-pick" : "") : (o.rank === 1 ? "top" : ""));
  const rows = options.map((o) => (mode === "baseline"
    ? `<tr class="${rowCls(o)}"><td>${esc(o.id)}${tags(o)}</td><td>${o.rank}</td><td>${esc(shiftWords(o.change_text))}</td><td>${esc(o.description)}</td><td>${esc(o.nurse)}</td>` +
      `<td>${o.contract_h.toFixed(1)}</td><td>${o.hours_period.toFixed(1)}</td><td>${o.n_changes}</td><td>${applyBtn(o)}</td></tr>`
    : `<tr class="${rowCls(o)}"><td>${esc(o.id)}${tags(o)}</td><td>${o.rank}</td><td>${o.rank_baseline}</td><td>${esc(shiftWords(o.change_text))}</td><td>${esc(o.description)}</td>` +
      METRICS.map((m) => `<td>${o.nurses.map((n) => metricCell(n, m)).join("<br>")}</td>`).join("") +
      `<td>${o.delta_strain.toFixed(2)}</td><td>${applyBtn(o)}</td></tr>`)).join("");
  el.innerHTML = `<table class="opts">${head}${rows}</table>`;
  el.querySelectorAll("button[data-opt]").forEach((b) =>
    b.addEventListener("click", () => guarded(() => applyOption(options.find((o) => o.id === b.dataset.opt)))));
}

function renderGrid() {
  const g = $("#grid");
  if (!state) { g.innerHTML = ""; return; }
  const key = ([n, d]) => `${n}|${d}`;
  const leave = new Set(state.leave.map(key));
  const absent = new Set(state.absent.map(key));
  const changed = new Set(state.changed.map(key));
  const focus = focusNurses();
  const ev = state.event;
  let html = "<tr><th></th>" + Array.from({ length: state.days }, (_, d) => `<th class="${d % 7 === 0 ? "wk" : ""}">${d + 1}</th>`).join("") + "</tr>";
  for (const n of state.nurses) {
    html += `<tr class="${focus.has(n.id) ? "focus" : ""}"><th>${n.id}${n.senior ? "★" : ""}</th>`;
    for (let d = 0; d < state.days; d++) {
      const k = `${n.id}|${d}`;
      const s = (state.grid[n.id] || {})[d] || "";
      let cls = s ? `s-${s}` : "";
      let txt = s;
      if (leave.has(k)) { cls = "leave"; txt = "L"; }
      if (absent.has(k)) { cls = "absent"; txt = "X"; }
      if (changed.has(k)) cls += " changed";
      if (ev && ev.absent === n.id && ev.day === d) cls += " event";
      if (d % 7 === 0) cls += " wk";
      html += `<td class="${cls}">${txt}</td>`;
    }
    html += "</tr>";
  }
  g.innerHTML = html;
}

function renderStrain() {
  if (!state) return;
  const k = state.kpis;
  $("#ward-kpis").textContent = `Window (±28 days): tiredness inequality ${k.gini.toFixed(3)} (0 = equal) · top 10% of nurses carry ${(k.top10_qr_share * 100).toFixed(0)}% of quick returns · most quick returns on one nurse: ${k.max_qr}`;
  if (!window.Chart) return;
  const rows = [...state.strain].sort((a, b) => b.strain - a.strain);
  const focus = focusNurses();
  const data = {
    labels: rows.map((r) => r.nurse),
    datasets: [{ label: "Tiredness score (window)", data: rows.map((r) => r.strain),
      backgroundColor: rows.map((r) => (focus.has(r.nurse) ? "#d97706" : "#1f6feb")) }],
  };
  if (chart) { chart.data = data; chart.update(); return; }
  chart = new Chart($("#strain-chart"), { type: "bar", data, options: { animation: false,
    plugins: { legend: { display: false } }, scales: { x: { ticks: { autoSkip: false, maxRotation: 90, font: { size: 9 } } } } } });
}

async function loadPolicy() {
  const p = await api("/api/policy");
  weights = p.weights;
  policyForm = p;
  $("#policy-form").innerHTML = METRICS.map((m) =>
    `<label title="${esc(METRIC_TIP[m])}">Points per: ${esc(METRIC_LABEL[m])}<br><input type="number" step="0.5" min="0" name="${m}" value="${p.weights[m]}"></label>`).join("") +
    `<label>Days to look ahead<br><input type="number" min="1" max="28" name="forward_days" value="${p.forward_days}"></label>` +
    `<label><input type="checkbox" name="squared" ${p.squared ? "checked" : ""}> Penalise piling load on a few nurses</label>` +
    '<button type="submit" class="primary">Save policy</button>';
}

async function savePolicy(ev) {
  ev.preventDefault();
  const f = new FormData(ev.target);
  discardProposal();
  const body = {
    weights: Object.fromEntries(METRICS.map((m) => [m, Number(f.get(m))])),
    forward_days: Number(f.get("forward_days")),
    squared: f.get("squared") === "on",
  };
  await putPolicy(body, "Policy saved — options re-ranked");
}

async function putPolicy(body, msg) {
  const p = await api("/api/policy", { method: "PUT", body: JSON.stringify(body) });
  weights = p.weights;
  await loadPolicy();
  state = await api("/api/state");
  toast(msg);
  await loadOptions();
  render();
  await loadAudit();
}

async function translatePolicy() {
  const text = $("#policy-text").value.trim();
  if (!text) { toast("Write the policy in words first."); return; }
  proposal = null;
  $("#translate-result").innerHTML = "";
  $("#translate-status").textContent = "GenAI is translating…";
  $("#btn-translate").disabled = true;
  try {
    const r = await api("/api/policy/translate", { method: "POST", body: JSON.stringify({ text }) });
    if (!r.proposal) {
      $("#translate-status").textContent = "";
      $("#translate-result").textContent = `GenAI translation unavailable — set the weights manually above. ${r.error || ""}`;
      return;
    }
    proposal = { weights: r.proposal.weights, text };
    $("#translate-status").innerHTML = `<span class="src">${esc(r.source)} · ${r.latency_ms} ms</span>`;
    const rows = METRICS.map((m) => {
      const cur = r.current[m], nw = r.proposal.weights[m];
      return `<tr><td>${esc(METRIC_LABEL[m])}</td><td>${cur}</td><td class="${cur !== nw ? "changed" : ""}">${nw}</td></tr>`;
    }).join("");
    $("#translate-result").innerHTML = `<table class="cmp"><tr><th>Item</th><th>Current</th><th>Proposed</th></tr>${rows}</table>` +
      '<p id="translate-rationale"></p><div><button type="button" id="btn-apply-proposal" class="primary">Apply proposed weights</button>' +
      '<button type="button" id="btn-discard-proposal">Discard</button></div>';
    $("#translate-rationale").textContent = r.proposal.rationale_plain ?? r.proposal.rationale;
    $("#btn-apply-proposal").addEventListener("click", () => guarded(applyProposal));
    $("#btn-discard-proposal").addEventListener("click", discardProposal);
  } finally {
    $("#btn-translate").disabled = false;
    if ($("#translate-status").textContent === "GenAI is translating…") $("#translate-status").textContent = "";
  }
}

function discardProposal() {
  proposal = null;
  $("#translate-result").innerHTML = "";
  $("#translate-status").textContent = "";
}

async function applyProposal() {
  if (!proposal) return;
  const p = policyForm || (await api("/api/policy"));
  const body = { weights: proposal.weights, forward_days: p.forward_days, squared: p.squared,
    source: "genai", policy_text: proposal.text };
  await putPolicy(body, "Proposed weights applied — options re-ranked");
  discardProposal();
}

// ---- Two-page presenter view ------------------------------------------------------------------
let resultsData = null;
let resChart = null;

function pageFromUrl() {
  const q = new URLSearchParams(location.search).get("page");
  if (q === "results" || location.hash === "#results") return "results";
  if (q === "one" || location.hash === "#one") return "one";
  try { return localStorage.getItem("roster-page") === "results" ? "results" : "one"; } catch (e) { return "one"; }
}

function setPage(p) {
  document.body.classList.toggle("pg-results", p === "results");
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.page === p));
  try { localStorage.setItem("roster-page", p); } catch (e) { /* storage unavailable */ }
  if (p === "results") guarded(loadResults);
}

const fmtNum = (v, dec = 1) => String(Number(v.toFixed(dec)));

async function loadResults() {
  if (!resultsData) resultsData = await api("/api/results");
  renderResults(resultsData);
}

function renderResults(r) {
  const na = !r || !r.available;
  $("#res-title").textContent = na ? "Results across all wards" : `Results across ${r.n_wards} simulated wards (8 weeks each, same sick calls for every method)`;
  $("#res-chart-box").classList.toggle("hidden", na);
  if (na) {
    $("#res-hero").textContent = "";
    $("#res-table").innerHTML = '<p class="res-na">Results not available yet</p>';
    $("#res-rel").innerHTML = ""; $("#res-foot").textContent = "";
    return;
  }
  const n = r.n_wards;
  const ge3 = r.metrics.find((m) => m.key === "nurses_qr_ge3_28d");
  if (ge3 && ge3.change_pct !== null) {
    const x = Math.round(Math.abs(ge3.change_pct));
    $("#res-hero").textContent = `Rule ranks, GenAI explains: ${x}% ${ge3.change_pct <= 0 ? "fewer" : "more"} nurses with 3+ quick returns in 4 weeks — better on ${ge3.wins} of ${n} wards.`;
  } else $("#res-hero").textContent = "";
  const cell = (side, key) => { if (!side) return '<span class="flat">–</span>'; const d = key === "changes_per_repair" ? 2 : 1;
    return `${fmtNum(side.mean, d)}<span class="rng">(range ${fmtNum(side.min, d)}–${fmtNum(side.max, d)})</span>`; };
  const chg = (m) => { if (m.change_pct === null) return '<span class="flat">–</span>';
    const v = Math.round(m.change_pct);
    return `<span class="${v < 0 ? "good" : v > 0 ? "badc" : "flat"}">${v > 0 ? "+" : v < 0 ? MINUS : ""}${Math.abs(v)}%</span>`; };
  const rows = r.metrics.map((m) => `<tr class="${m.cost ? "cost" : ""}"><td>${esc(m.label)}${m.cost ? ' <span class="tag-cost">(the cost)</span>' : ""}</td>` +
    `<td class="num">${cell(m.baseline, m.key)}</td><td class="num">${cell(m.ours, m.key)}</td><td class="num">${chg(m)}</td>` +
    `<td class="num">${m.wins} of ${n}${m.ties ? ` <span class="tag-cost">(${m.ties} tied)</span>` : ""}</td>` +
    `<td class="num exp">${cell(m.exp, m.key)}</td></tr>`).join("");
  $("#res-table").innerHTML = `<table class="res"><tr><th>Metric</th><th class="num">Today's software</th><th class="num">Rule ranks, GenAI explains</th>` +
    `<th class="num">Change</th><th class="num">Wards where the rule is better</th><th class="num exp">GenAI chooses (experimental)</th></tr>${rows}</table>`;
  renderResultsChart(r);
  const e = r.explanations, parts = [];
  if (e) {
    if (e.fact_check_pass_rate != null) parts.push(`Fact check passed for <b>${Math.round(e.fact_check_pass_rate * 100)}%</b> of explanations`);
    if (e.direction_error_rate != null) parts.push(`wording direction wrong in <b>${Math.round(e.direction_error_rate * 100)}%</b>`);
    if (e.valid_output_rate != null) parts.push(`valid output <b>${Math.round(e.valid_output_rate * 100)}%</b>`);
    if (e.mean_latency_s != null) parts.push(`about <b>${Math.round(e.mean_latency_s)} s</b> per explanation`);
  }
  $("#res-rel").innerHTML = parts.length ? `<div class="rel-title">How reliable are GenAI's explanations? (${esc(e.model ?? "")}, ${e.n_decisions ?? "?"} decisions)</div>${parts.join('<span class="sep">·</span>')}` +
    '<p class="muted">GenAI never changes the ranking or the choice — if it fails, the rule\'s choice stands.</p>' : "";
  $("#res-rel").classList.toggle("hidden", !parts.length);
  $("#res-foot").textContent = "Simulated wards built from Erasmus MC and Dutch parameters. The experimental column replays the GenAI-chooser run" +
    (r.model ? ` (${r.model}).` : ".");
}

function renderResultsChart(r) {
  const keys = ["QR_total", "nurses_qr_ge3_28d", "max_qr"];
  const names = { QR_total: "Quick returns", nurses_qr_ge3_28d: "Nurses with 3+ quick returns", max_qr: "Most quick returns for one nurse" };
  const ms = keys.map((k) => r.metrics.find((m) => m.key === k)).filter(Boolean);
  const avg = ms.map((m) => (m.change_pct === null ? null : Number(m.change_pct.toFixed(1))));
  $("#res-cap").textContent = "Rule-ranked vs today's software, average change across all wards: below zero means fewer, which is better.";
  if (!window.Chart) return;
  const data = { labels: ms.map((m) => names[m.key]), datasets: [
    { label: "Average of all wards", data: avg, backgroundColor: "#15803d" }] };
  if (resChart) { resChart.destroy(); resChart = null; }
  resChart = new Chart($("#res-chart"), { type: "bar", data, options: { animation: false, maintainAspectRatio: false,
    plugins: { legend: { position: "bottom" }, title: { display: true, text: "Change vs today's software (%)" },
      tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y}%` } } },
    scales: { y: { ticks: { callback: (v) => `${v}%` }, suggestedMax: 5 } } } });
}

// ---- GenAI autoplay --------------------------------------------------------------------------
const BUSY_SELECTORS = "#btn-start, #btn-view, #btn-new, #btn-next, #btn-ff, #btn-auto, #btn-autoplay, #auto-n, #policy-form button, #btn-apply-proposal, #btn-translate, #btn-override-main, .mode";
const WHO = { ai: "GenAI (experimental)", strain: "the hospital rule", baseline: "today's software" };

function setBusy(running) {
  autoRunning = running;
  document.querySelectorAll(BUSY_SELECTORS).forEach((b) => { b.disabled = running; });
  document.querySelectorAll("#options button[data-opt]").forEach((b) => { b.disabled = running; });
}

function renderAutoItem(it) {
  const li = document.createElement("li");
  li.className = "auto-item";
  const pv = isPresenter();
  const line = document.createElement("div");
  if (pv) {
    const by = /fallback/.test(it.by) ? "Backup choice" : it.by === "Formula" ? "Hospital rule" : it.by === "ORTEC-like" ? "Today's software" : String(it.by);
    line.textContent = niceNurse(`Sick call: ${it.absent} — ${String(it.shift).toLowerCase()} shift, day ${it.day} → ${by}: ${it.description ?? it.chosen_change_text}`);
  } else {
    const nurse = it.chosen_nurse ? `${it.chosen_nurse} (${it.chosen})` : it.chosen;
    const by = String(it.by).replace(/^Formula/, RULE).replace(/^ORTEC-like/, "Today's software");
    line.textContent = `Sick call: ${it.absent} — ${String(it.shift).toLowerCase()} shift, day ${it.day} → ${by} gave it to ${nurse}. `;
    const verdict = document.createElement("span");
    verdict.textContent = it.agrees_with_formula ? "✅ same as hospital rule check" : `⚠️ hospital rule check preferred ${it.formula_top}`;
    line.appendChild(verdict);
  }
  li.appendChild(line);
  if (!pv && it.chosen_change_text) {
    const chg = document.createElement("div");
    chg.className = "muted";
    chg.textContent = it.chosen_change_text;
    li.appendChild(chg);
  }
  if (it.display_text) {
    const txt = document.createElement("div");
    txt.className = "muted x-expert";
    txt.textContent = it.display_text;
    li.appendChild(txt);
  }
  return li;
}

function renderAuto(s) {
  $("#auto-card").classList.remove("hidden");
  const who = WHO[autoMode] ?? "GenAI";
  $("#auto-title").textContent = `${who.charAt(0).toUpperCase()}${who.slice(1)} at work`;
  $("#auto-head").textContent = s.running ? `${who.charAt(0).toUpperCase()}${who.slice(1)} is handling sick call ${Math.min(s.done + 1, s.total)} of ${s.total}…`
    : s.error ? `Stopped after ${s.done} of ${s.total}: ${s.error}`
    : `Handled ${s.done} of ${s.total} sick calls`;
  $("#auto-bar").max = Math.max(s.total, 1);
  $("#auto-bar").value = s.done;
  $("#btn-auto-stop").classList.toggle("hidden", !s.running);
  $("#auto-list").replaceChildren(...s.log.slice().reverse().map(renderAutoItem));
}

async function pollAutoplay() {
  autoTimer = null;
  let s;
  try { s = await api("/api/autoplay/status"); } catch (e) { toast(e.message); autoTimer = setTimeout(pollAutoplay, 1500); return; }
  renderAuto(s);
  try {
    state = await api("/api/state");
    options = []; comparison = null;
    hideExplanation();
    render();
  } catch (e) { toast(e.message); }
  if (s.running) { autoTimer = setTimeout(pollAutoplay, 1500); return; }
  setBusy(false);
  toast(s.error ? `Autoplay stopped: ${s.error}` : `${WHO[autoMode] ? WHO[autoMode].replace(/^./, (c) => c.toUpperCase()) : "GenAI"} handled ${s.done} sick calls`);
  await loadOptions();
  render();
  await loadAudit();
}

function watchAutoplay() {
  setBusy(true);
  if (autoTimer === null) pollAutoplay();
}

async function startAutoplay() {
  const events = Number($("#auto-n").value);
  autoMode = mode;
  options = []; comparison = null;
  hideExplanation();
  await api("/api/autoplay", { method: "POST", body: JSON.stringify({ events, mode }) });
  watchAutoplay();
  render();
}

async function stopAutoplay() {
  await api("/api/autoplay/stop", { method: "POST" });
  toast("Stopping after the current sick call.");
}

async function loadAudit() {
  const rows = (await api("/api/audit")).entries.slice(-15).reverse();
  const line = (r) => r.mode === "policy"
    ? `<tr><td>${esc(r.ts.slice(11, 19))}</td><td>—</td><td>Policy</td><td>weights updated (${esc(r.source ?? "manual")})</td><td></td><td></td><td>${esc(r.policy_text ?? "")}</td></tr>`
    : `<tr><td>${esc(r.ts.slice(11, 19))}</td><td>${r.event_id}</td><td>${esc(MODE_LABEL[r.mode] ?? r.mode)}${r.fallback ? " (fallback)" : ""}</td>` +
      `<td>${esc(r.option_id ?? "unfilled")}</td><td>${esc(r.top_option ?? "")}</td><td>${esc(r.override_reason ?? "")}</td>` +
      `<td>${esc(r.explanation_source ?? "")}${r.verified === false ? " ⚠️" : ""}</td></tr>`;
  $("#audit").innerHTML = "<tr><th>Time</th><th>Sick call</th><th>Mode</th><th>Chosen</th><th>Top</th><th>Override</th><th>Explanation</th></tr>" +
    rows.map(line).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  $("#btn-start").addEventListener("click", () => guarded(startPresenter));
  $("#btn-apply-main").addEventListener("click", () => guarded(applyMain));
  $("#btn-override-main").addEventListener("click", () => guarded(overrideMain));
  $("#btn-view").addEventListener("click", () => guarded(() => setView(isPresenter() ? "expert" : "presenter")));
  $("#btn-new").addEventListener("click", () => guarded(newScenario));
  $("#btn-next").addEventListener("click", () => guarded(nextEvent));
  $("#btn-ff").addEventListener("click", () => guarded(() => fastForward({ to_day: Number($("#ff-week").value) })));
  $("#btn-auto").addEventListener("click", () => guarded(() => fastForward({ events: 10 })));
  document.querySelectorAll(".mode").forEach((b) => b.addEventListener("click", () => guarded(() => setMode(b.dataset.mode))));
  $("#policy-form").addEventListener("submit", (e) => guarded(() => savePolicy(e)));
  $("#btn-translate").addEventListener("click", () => guarded(translatePolicy));
  $("#btn-autoplay").addEventListener("click", () => guarded(startAutoplay));
  $("#btn-auto-stop").addEventListener("click", () => guarded(stopAutoplay));
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => setPage(b.dataset.page)));
  window.addEventListener("hashchange", () => setPage(pageFromUrl()));
  setPage(pageFromUrl());
  guarded(async () => {
    state = await api("/api/state");
    await loadPolicy();
    if (state.autoplay_running) autoRunning = true;
    defaultMode = state.default_mode || "strain";
    await setView(storedView());
    await setMode(defaultMode);
    render();
    await loadAudit();
    if (state.autoplay_running) watchAutoplay();
  });
});
