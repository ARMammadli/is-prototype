"use strict";
const $ = (sel) => document.querySelector(sel);
const METRICS = ["QR", "N", "LR", "OT", "SN"];
const METRIC_LABEL = { QR: "Quick returns (<11 h rest)", N: "Night shifts", LR: "Long runs (6+ days)", OT: "Overtime hours", SN: "Short-notice changes (<48 h)" };
const METRIC_TIP = {
  QR: "Quick return: back at work after less than 11 hours' rest between two shifts",
  N: "Number of night shifts worked in the past and next 28 days",
  LR: "Long run: 6 or more working days in a row",
  OT: "Overtime hours: hours worked above the nurse's contract",
  SN: "Short-notice change: any shift change, a move or a call-in, made with less than 48 hours' notice",
};
const TRADEOFF_WORD = { quick_returns: "quick returns", nights: "night shifts", long_runs: "long runs", overtime: "overtime",
  short_notice: "short-notice changes", stability: "stability (few changes)", concentration: "load concentrated on a few nurses" };
const tradeoffWord = (t) => TRADEOFF_WORD[t] ?? String(t ?? "").replaceAll("_", " ");
const SHIFT_WORD = { D: "day", E: "evening", N: "night" };
const shiftWords = (s) => String(s ?? "").replace(/(^|: |→ |; )([DEN])\b/g, (_, p, c) => `${p}${SHIFT_WORD[c]} shift`);
const TODAY = "Today's software (ORTEC-style)";
const MODE_LABEL = { baseline: TODAY, strain: "Rule ranks, GenAI explains", auto: "Auto (hospital rule)", "auto-strain": "Hospital rule autoplay", "auto-baseline": "Today's software autoplay", policy: "Policy" };
const oursLabel = () => "Hospital rule";
const oursShort = () => "the hospital rule";
const LOWER = ' <span class="metric-hint">(lower is better)</span>';
// Display backstop for the presenter view: no "Option_N" ids, no "Nurse_NN" ids anywhere.
const noOptionIds = (s) => String(s ?? "").replace(/\bOption_0*(\d+)\b/gi, (_, n) => { const d = descOf(`Option_${Number(n)}`); return d ? `“${d}”` : "another option"; });
const niceNurse = (s) => noOptionIds(String(s ?? "").replace(/Nurse_(\d+)/g, "Nurse $1"));
const MINUS = "\u2212";
// Simple navy line icons (replace emoji, which look informal on slides). Stroke uses currentColor.
const ICON_PATHS = {
  pulse: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  play: '<polygon points="7 4 20 12 7 20 7 4"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  thermo: '<path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  sunset: '<path d="M17 18a5 5 0 0 0-10 0"/><path d="M12 9V2M4.2 10.2l1.4 1.4M1 18h2M21 18h2M18.4 11.6l1.4-1.4M23 22H1"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
  scale: '<path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/>',
  list: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M9 12h6M9 16h6"/>',
  warn: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  checkCircle: '<circle cx="12" cy="12" r="10"/><polyline points="16.5 9 10.5 15 7.5 12"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
};
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;
const AI_TAG = '<span class="ai-tag" title="Written by GenAI">AI</span>';
// Server text may carry emoji markers; the UI shows an icon instead.
const stripMarks = (s) => String(s ?? "").replace(/\s*(⚠️|⚠|✓|✅)\s*/g, " ").trim();
const signedWord = (n) => (n > 0 ? `+${n}` : n < 0 ? `${MINUS}${-n}` : "0");
function factsBadge(verified, presenter) {
  return verified ? `<span class="badge ok">${icon("check")}Summary checked against the facts</span>`
    : `<span class="badge bad">${icon("warn")}Flagged: summary did not match the facts, hidden</span>`;
}
const shortNotice = (h) => h < 48;
let autoRunning = false;
let autoMode = "strain";
let autoTimer = null;
let mode = "strain";
let llmMode = "live";  // "replay": GenAI answers were pre-generated locally; the model is not on this server
let explanation = null;
let explainPending = false;
let explainError = null;
let state = null;
let options = [];
let chart = null;
let scoreChart = null;
let comparison = null;
let weights = null;
let policyForm = null;
let proposal = null;
let reqToken = 0;
let applying = false;
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
}

function hideExplanation() {
  $("#explain-card").classList.add("hidden");
  explanation = null;
  explainPending = false;
  explainError = null;
  reqToken++;
}

function formulaTopId() { const t = options.find((o) => o.rank === 1); return t ? t.id : null; }
const optName = (id) => String(id ?? "");
function descOf(id) {
  const o = options.find((x) => x.id === id);
  if (o && o.description) return o.description;
  const c = comparison;
  if (c && c.ours.id === id) return c.ours.description;
  if (c && c.ortec.id === id) return c.ortec.description;
  return null;
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

// GenAI explains the rule's choice. The choice is already made: accept is enabled before this returns,
// and if GenAI fails the ranked table stays without a narrative (the server logs the failure at apply).
const EXPLAIN_UNAVAILABLE = "GenAI unavailable, facts shown. The rule's choice and its facts do not need GenAI.";
const NOT_RECORDED = "Not pre-generated for this case: GenAI is not deployed on this server, so the rule's facts are shown.";
const genaiMissText = (r, fallback) => (r && r.not_recorded ? NOT_RECORDED : fallback);
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
    $("#explain-text").textContent = EXPLAIN_UNAVAILABLE;
    $("#explain-text").title = e.message;
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
    $("#explain-text").textContent = r.not_recorded ? NOT_RECORDED : EXPLAIN_UNAVAILABLE + (r.error ? ` (${r.error})` : "");
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
  const needsReason = opt.rank !== 1;
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
  const top = formulaTopId();
  const others = options.filter((o) => o.id !== top);
  if (!others.length) { toast("There is no other option for this sick call."); return; }
  const a = await askReason(others);
  if (!a) return;
  const opt = options.find((o) => o.id === a.option);
  if (opt) await applyOption(opt, a.reason);
}

async function applyMain() {
  const id = formulaTopId();
  const opt = options.find((o) => o.id === id);
  if (!opt) { toast("The rule's choice is not among the current options. Refresh with Next sick call."); return; }
  await applyOption(opt);
}

function renderApplyMain() {
  const btn = $("#btn-apply-main"), st = $("#apply-status");
  if (!btn) return;
  $("#btn-override-main").disabled = applying || autoRunning || options.length < 2 || mode === "baseline";
  // Accept is available at once; GenAI's explanation never gates it.
  btn.innerHTML = `${icon("check")}Accept the rule's choice`;
  btn.disabled = applying || autoRunning || !options.length || mode === "baseline";
  if (explainPending) st.innerHTML = '<span class="spinner"></span>GenAI is writing an explanation…';
  else st.textContent = "";
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
  if (v === "presenter" && mode === "baseline") await setMode("strain");
  else if (state) render();
}

async function startPresenter() {
  setPage("one");
  $("#btn-start").disabled = true;
  try { await startPresenterInner(); } finally { $("#btn-start").disabled = autoRunning; }
}

// Shows whether the local model is reachable. Without it the app still runs: the rule decides and its
// facts are shown; only the GenAI wording, report narrative and policy proposal are missing.
async function llmStatus() {
  try {
    const r = await api("/api/llm-status");
    const el = $("#llm-status");
    llmMode = r.mode || "live";
    const replay = llmMode === "replay";
    el.innerHTML = !r.available ? `${icon("warn")} GenAI unavailable, facts shown`
      : replay ? `${icon("check")} GenAI answers pre-generated locally (${esc(r.model)})` : `${icon("check")} GenAI online (${esc(r.model)})`;
    el.title = replay ? "The model could not be deployed on this server. Its answers were generated beforehand on a local machine with the same prompts and are replayed here; cases that were not pre-generated show the rule's facts only." : "";
    el.classList.toggle("off", !r.available);
    if (replay) {
      $("#foot-genai").textContent = `GenAI answers pre-generated locally (${r.model}), the model is not deployed on this server`;
      $("#seed-box").classList.add("hidden");  // only the five wards in Setup were pre-generated
    }
  } catch (e) { /* status is informational only */ }
}

// Demo Day: same seed, default weights, the day-4 sick call, policy box pre-filled.
async function startDemo() {
  setPage("one");
  await setView("presenter");
  state = await api("/api/demo", { method: "POST" });
  options = []; comparison = null; proposal = null;
  hideExplanation();
  await loadPolicy();
  $("#policy-text").value = state.demo_policy_text || "";
  $("#translate-result").innerHTML = ""; $("#translate-status").textContent = "";
  await loadOptions();
  render();
  await loadAudit();
  toast("Demo ready: ward 1, day 4, Nurse 43 called in sick.");
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

const SHIFT_ICON = { D: icon("sun"), E: icon("sunset"), N: icon("moon") };
const SHIFT_TIME = { D: "07:30–16:00", E: "15:30–23:00", N: "23:00–07:30" };
function sickHero(ev, sh) {
  const shiftName = `${sh.charAt(0).toUpperCase()}${sh.slice(1)} shift`;
  const total = state && state.days ? ` of ${state.days}` : "";
  const notice = shortNotice(ev.notice_h) ? `<span class="chip warn">${icon("clock")}Only ${Math.round(ev.notice_h)} h notice</span>` : "";
  const tail = ev.unfilled ? '<div class="sick-q warn">No one can legally take this shift. It runs short.</div>'
    : '<div class="sick-q">Someone has to cover this shift. Who should it be?</div>';
  return `<div class="sick-hero"><div class="sick-icon">${icon("thermo")}</div><div class="sick-body">` +
    `<div class="sick-who"><b>${esc(niceNurse(ev.absent))}</b> called in sick</div>` +
    `<div class="chips"><span class="chip">${SHIFT_ICON[ev.shift] ?? ""} ${esc(shiftName)} · ${SHIFT_TIME[ev.shift] ?? ""}</span>` +
    `<span class="chip">${icon("calendar")}Day ${ev.day + 1}${total}</span>${notice}</div>${tail}</div></div>`;
}

function renderEvent() {
  $("#remaining").textContent = state ? `${state.remaining_events} sick calls left · ${state.unfilled.length} unfilled` : "";
  const ev = state && state.event;
  const el = $("#event");
  $("#btn-next").classList.toggle("hidden", !state || (!!ev && !ev.unfilled) || autoRunning);
  if (!ev) { el.textContent = autoRunning ? "GenAI is working through the sick calls…" : state ? "No open sick call. Press “Next sick call”." : "Pick a ward and press Start."; return; }
  const sh = SHIFT_WORD[ev.shift] ?? ev.shift;
  if (isPresenter()) { el.innerHTML = sickHero(ev, sh); return; }
  el.innerHTML = `<b>${esc(ev.absent)}</b> called in sick: <b>${sh.charAt(0).toUpperCase()}${sh.slice(1)} shift</b>, day <b>${ev.day + 1}</b>` +
    (shortNotice(ev.notice_h) ? " (short notice)" : "") +
    (ev.unfilled ? '<div class="warn">No feasible repair option. The shift runs short.</div>' : "");
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
  const b = state.preview.baseline, s = state.preview.strain;
  const fix = (m) => (m ? Number(m.changes_per_repair.toFixed(2)) : null);
  const pv = isPresenter();
  const rows = [
    ["Nurses with 3+ quick returns in any 28 days", "nurses_qr_ge3_28d", true],
    ["Quick returns in total", "QR_total", true],
    ["Most quick returns on one nurse", "max_qr"],
    ["Unfilled shifts", "unfilled", true],
    ["Short-notice changes", "SN_total"],
    ["Changes per repair", "changes_per_repair"],
  ].filter((r) => !pv || r[2]);
  const val = (m, k) => (m ? (k === "changes_per_repair" ? fix(m) : m[k]) : null);
  const thead = `<tr><th></th><th>${TODAY}</th><th>${RULE}</th></tr>`;
  const body = rows.map(([l, k]) => {
    const vals = [val(b, k), val(s, k)];
    const cls = bestClasses(vals);
    return `<tr><td>${l}${LOWER}</td>${vals.map((v, i) => `<td class="${cls[i]}">${v}</td>`).join("")}</tr>`;
  }).join("");
  const note = b.unfilled === s.unfilled ? "Same coverage. The difference is who carries the load."
    : `Coverage (unfilled shifts): today's software ${b.unfilled} · hospital rule ${s.unfilled}`;
  el.innerHTML = `<table class="cmp">${thead}${body}</table><p class="banner-note">${note}</p>`;
}

function compareRows(r, o, thead) {
  const qr = (v) => (v < 0 ? `removes ${-v}` : String(v));
  const mv = (m) => (m ? `${esc(m.nurse)}: load score ${m.before} → ${m.after}` : "nobody");
  const row = (label, fr, fo) => `<tr><td>${label}</td><td>${fr}</td><td>${fo}</td></tr>`;
  return `<table class="cmp">${thead}` +
    row("Option", esc(optName(r.id)), esc(optName(o.id))) +
    row("Change", esc(shiftWords(r.change_text)), esc(shiftWords(o.change_text))) +
    row("What happens", esc(r.description), esc(o.description)) +
    row(`New quick returns${LOWER}`, qr(r.new_quick_returns), qr(o.new_quick_returns)) +
    row("Who gets extra work", mv(r.extra_work), mv(o.extra_work)) +
    row("Who gets relief", mv(r.relief), mv(o.relief)) +
    row(`People disturbed${LOWER}`, r.people_disturbed, o.people_disturbed) + "</table>";
}

function cardHtml(title, lines, rest, cls, tag, how, ico) {
  const [act, ...others] = lines;
  const restHtml = (rest || []).map((l) => { const bad = l.includes("⚠");
    return `<p class="rest ${bad ? "bad" : "good"}">${icon(bad ? "warn" : "check")}<span>${bad ? "Warning: " : ""}${esc(niceNurse(stripMarks(l)))}</span></p>`; }).join("");
  const tagHtml = tag && isPresenter() ? `<span class="ctag">${esc(tag)}</span>` : "";
  const howHtml = how && isPresenter() ? `<p class="how">${esc(how)}</p>` : "";
  return `<div class="choice ${cls}"><h3><span class="ttl">${ico ? icon(ico) : ""}${esc(title)}</span>${tagHtml}</h3>${howHtml}<p class="act">${esc(niceNurse(act))}</p>${restHtml}` +
    others.map((l) => `<p class="${l.startsWith("Cost") ? "cost" : ""}">${esc(niceNurse(l))}</p>`).join("") + "</div>";
}

// Presenter view: two side-by-side choice cards built from the server's deterministic card_lines.
function explainBubble() {
  if (explainPending) return `<div class="box"><div class="box-head">${AI_TAG}GenAI summary</div><div class="box-body"><p class="muted"><span class="spinner"></span>GenAI is writing a summary… (you can already accept)</p></div></div>`;
  const r = explanation;
  if (explainError || (r && !r.explanation && !r.fact_block)) return `<div class="box"><div class="box-head">${AI_TAG}GenAI summary</div><div class="box-body"><p class="muted">${esc(EXPLAIN_UNAVAILABLE)}</p></div></div>`;
  if (!r) return "";
  if (r.fact_block) {
    // Final design (E10): the rule's facts are always shown; GenAI's one-line summary only restates them and is
    // shown only when the check passes. A flagged summary is hidden, so the planner sees the rule's facts only.
    const facts = r.fact_block.map((f) => `<li>${esc(niceNurse(f))}</li>`).join("");
    const shown = r.show_summary ?? (r.framing && r.check.verified);
    const body = shown ? `<p>${esc(niceNurse(r.framing))}</p>${factsBadge(true, true)}`
      : r.framing ? `<p class="muted">${icon("warn")} Flagged: GenAI summary hidden because it did not match the facts. The facts above are complete.</p>`
        : `<p class="muted">${esc(EXPLAIN_UNAVAILABLE)}</p>`;
    return `<div class="box"><div class="box-head">${icon("list")}Facts <span class="src-tag">written by the hospital rule from the roster data</span></div><div class="box-body"><ul class="facts">${facts}</ul></div></div>` +
      `<div class="box"><div class="box-head">${AI_TAG}GenAI summary <span class="src-tag">restates the facts above, nothing else</span></div><div class="box-body">${body}</div></div>`;
  }
  const text = niceNurse(r.display_text ?? r.explanation.text);
  return `<div class="box"><div class="box-head">${AI_TAG}GenAI explains the rule's choice</div><div class="box-body"><p>${esc(text)}</p>${factsBadge(r.check.verified, true)}</div></div>`;
}

// The one-look summary for the scheduler: what the rule recommends, what it improves, what it costs, and why.
function recoBanner(lines, rest, same, diffText) {
  const act = niceNurse(lines ? lines.ours[0] : comparison.ours.description);
  const points = [];
  (rest.ours || []).filter((l) => !l.includes("⚠") && !/everyone keeps/.test(l))
    .forEach((l) => points.push(`<span class="pt good-txt">${icon("check")}${esc(niceNurse(stripMarks(l)))}</span>`));
  if (!same) (rest.ortec || []).filter((l) => l.includes("⚠"))
    .forEach((l) => points.push(`<span class="pt good-txt">${icon("shield")}Avoids: ${esc(niceNurse(stripMarks(l)))}</span>`));
  (rest.ours || []).filter((l) => l.includes("⚠"))
    .forEach((l) => points.push(`<span class="pt bad-txt">${icon("warn")}Warning: ${esc(niceNurse(stripMarks(l)))}</span>`));
  const costLine = (lines ? lines.ours : []).find((l) => l.startsWith("Cost"));
  if (costLine) points.push(`<span class="pt bad-txt">${icon("warn")}${esc(niceNurse(costLine))}</span>`);
  const why = diffText ? `<p class="reco-why"><b>Why:</b> ${esc(diffText)} <span class="src-tag">(written by code from the roster data, not by GenAI)</span></p>` : "";
  return `<div class="reco"><div class="reco-ico">${icon("checkCircle")}</div><div class="reco-main">` +
    `<div class="reco-lbl">${same ? "Today's software and the hospital rule agree" : "The hospital rule recommends"}</div>` +
    `<div class="reco-act">${esc(act)}</div>${points.length ? `<div class="reco-points">${points.join("")}</div>` : ""}${why}</div></div>`;
}

function renderRuleCards() {
  const lines = comparison.card_lines;
  const rest = (lines && lines.rest_lines) || comparison.rest_lines || {};
  const ORTEC_HOW = "Looks for: free contract hours and the fewest shift changes. Does not look at anyone's recent shifts.";
  const RULE_HOW = "Ranks every legal option with the hospital's formula over five measures in the past and next 28 days: quick returns, nights, long runs, overtime and short-notice changes.";
  const ortec = cardHtml("Today's software", lines ? lines.ortec : [comparison.ortec.description], rest.ortec, "ortec", "Simplest fix", ORTEC_HOW, "monitor");
  const same = comparison.ours.id === comparison.ortec.id;
  const ours = cardHtml("Hospital rule's choice", lines ? lines.ours : [comparison.ours.description], rest.ours, "genai",
    same ? "Ranked #1 · same as today's software" : "Ranked #1", RULE_HOW, "scale");
  const diffText = niceNurse(comparison.difference || comparison.who_words || "");
  $("#compare").innerHTML = recoBanner(lines, rest, same, diffText) + `<div class="choice-cards vs-cards">${ortec}<div class="vs">vs</div>${ours}</div>`;
  const details = explainBubble();
  $("#genai-explains").innerHTML = details ? `<div class="details-title">Supporting details</div><div class="details-grid">${details}</div>` : "";
}

function renderCompare() {
  const card = $("#compare-card");
  renderApplyMain();
  $("#rule-line").textContent = "";
  if (!comparison || !options.length) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  const words = (c) => (isPresenter() ? niceNurse(c.who_words ?? c.plain_words) : c.plain_words);
  if (mode === "strain" && isPresenter()) {
    $("#compare-title").innerHTML = '<span class="step"><span class="num">2</span>Two ways to fill the gap: the rule ranks, you decide</span>';
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
    ? `Load score = ${w.QR} points per quick return, ${w.N} per night shift, ${w.LR} per long run of 6+ days, ${w.OT} per overtime hour, ${w.SN} per short-notice change (less than 48 hours' notice), counted in the past and next 28 days (weights set by the hospital). Higher = more recent load.`
    : "";
}

function countersHtml(st) {
  const o = st.ours, r = st.ortec;
  // Lower is better for both counters; the hospital rule's number is compared with today's software's.
  const side = (label, v, other, ours) => {
    const word = !ours ? "" : v < other ? `<span class="verdict good-txt">${icon("check")}better</span>`
      : v > other ? `<span class="verdict bad-txt">${icon("warn")}more</span>` : '<span class="verdict">same</span>';
    const cls = !ours ? "" : v < other ? "win" : v > other ? "bad" : "";
    return `<div class="side ${ours ? "ours" : ""}"><span class="who">${label}</span><span class="big ${cls}">${esc(signedWord(v))}</span>${word}</div>`; };
  const qr = (label, v, other, ours) => side(label, v, other, ours);
  const cost = (label, v, other, ours) => side(label, v, other, ours);
  return `<div class="counters">
    <div class="counter benefit"><div class="kind">The benefit</div><div class="what">Quick returns (under 11 h rest) on the whole roster</div><div class="pair">${qr("Today's software", r.quick_returns_change, o.quick_returns_change, false)}${qr(oursLabel(), o.quick_returns_change, r.quick_returns_change, true)}</div><div class="cap">Change since the first handled sick call, all nurses. Fewer is better.</div></div>
    <div class="counter price"><div class="kind">The price</div><div class="what">Short-notice changes (less than 48 hours' notice) on the whole roster</div><div class="pair">${cost("Today's software", r.extra_late_calls, o.extra_late_calls, false)}${cost(oursLabel(), o.extra_late_calls, r.extra_late_calls, true)}</div><div class="cap">One per nurse whose shift was changed at short notice, since the first handled sick call. Fewer is better.</div></div></div>`;
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
    $("#score-title").innerHTML = `<span class="step"><span class="num">4</span>Score so far: ${n} sick call${n === 1 ? "" : "s"} handled</span>`;
    $("#scoreboard").innerHTML = n ? '<p class="card-note">Whole roster, same sick calls for both. The sick call on screen is not counted until you accept it.</p>' + countersHtml(st)
      : `<p class="score-empty">Accept a choice or let ${oursShort()} handle the next sick calls. The score starts counting here.</p>`;
    more = st.ours.extra_late_calls > st.ortec.extra_late_calls;
  } else {
    $("#score-title").textContent = `This ward since ${oursShort()} took over`;
    const rows = [["Quick returns", "quick_returns", true], ["Nurses with 3+ quick returns in any 28 days", "nurses_qr_ge3_28d", true],
      ["Highest nurse load score", "max_load"], ["Short-notice changes", "short_notice_calls", true], ["Shifts changed", "shifts_changed"]];
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
  tr.textContent = more ? `The trade-off: ${oursShort()} makes more short-notice changes to spare nurses with a high recent load from short rests.` : "";
  if (!window.Chart || pres) return;
  const labels = [0, ...history.map((h) => h.n)];
  const first = start ? start.qr : null;
  const datasets = [
    { label: "Today's software", data: [first, ...history.map((h) => h.ortec_qr)], borderColor: "#86d2ed", backgroundColor: "#86d2ed", pointRadius: 0, tension: 0.2 },
    { label: oursLabel(), data: [first, ...history.map((h) => h.ours_qr)], borderColor: "#0c2074", backgroundColor: "#0c2074", pointRadius: 0, tension: 0.2 }];
  const data = { labels, datasets };
  if (scoreChart) { scoreChart.data = data; scoreChart.update(); return; }
  scoreChart = new Chart($("#score-chart"), { type: "line", data, options: { animation: false, maintainAspectRatio: false,
    plugins: { title: { display: true, text: "Quick returns after each sick call (lower is better)" }, legend: { position: "bottom" } },
    scales: { x: { title: { display: true, text: "Sick calls handled" } }, y: {} } } });
}

function applyBtn(o) {
  const dis = autoRunning ? " disabled" : "";
  return `<button${dis} data-opt="${esc(o.id)}" class="${o.rank === 1 ? "primary" : ""}">${o.rank === 1 ? "Apply (top)" : "Apply"}</button>`;
}

function metricCell(n, m) {
  const b = n.before[m];
  const a = n.after[m];
  return `<span class="${a > b ? "up" : ""}">${esc(n.nurse)}: ${b} → ${a}</span>`;
}

// Presenter: a compact ranked table (top 5): rule rank, what happens, strain cost, today's-software rank.
function renderOptionsCompact(el) {
  const ortecTop = options.find((o) => o.rank_baseline === 1);
  const rows = options.slice(0, 5).map((o) => {
    const tags = (o.rank === 1 ? '<span class="tag formula">Rule\'s choice</span>' : "") +
      (o.rank_baseline === 1 ? '<span class="tag">Today\'s software</span>' : "");
    return `<tr class="${o.rank === 1 ? "top" : ""}"><td><span class="rank">${o.rank}</span></td><td>${esc(niceNurse(o.description))}${tags}</td>` +
      `<td>${o.n_changes}</td><td>${signedWord(Number((o.strain_cost ?? 0).toFixed(1)))}</td><td>${o.rank_baseline}</td></tr>`;
  }).join("");
  const more = options.length > 5 ? `<p class="muted">+ ${options.length - 5} more legal options${ortecTop && ortecTop.rank > 5 ? ` (today's software's pick is ranked #${ortecTop.rank})` : ""}.</p>` : "";
  el.innerHTML = `<table class="opts"><tr><th>Rule rank</th><th>What happens</th><th>Shifts changed</th>` +
    `<th title="What the rule ranks by: the increase in the sum of squared load scores of the nurses involved, so adding load to a nurse who already carries a lot costs more">Strain cost (lower is better)</th><th>Today's software rank</th></tr>${rows}</table>${more}`;
}

function renderOptions() {
  const el = $("#options");
  if (!options.length) { el.innerHTML = ""; return; }
  if (isPresenter() && mode !== "baseline") { renderOptionsCompact(el); return; }
  const RANK_TIP = "Rank by the hospital rule (load score; 1 = recommended)";
  const ORTEC_TIP = "Rank by today's software: fewest changes, then contract fit";
  const head = mode === "baseline"
    ? `<tr><th>Option</th><th title="${ORTEC_TIP}">Today's software rank</th><th>Change</th><th>What happens</th><th>Nurse</th><th>Contract hours per week</th><th>Hours this period</th><th>Changes</th><th></th></tr>`
    : `<tr><th>Option</th><th title="${RANK_TIP}">Rule rank</th><th title="${ORTEC_TIP}">Today's software rank</th><th>Change</th><th>What happens</th>` + METRICS.map((m) => `<th title="${esc(METRIC_TIP[m])}">${esc(METRIC_LABEL[m])}</th>`).join("") + `<th title="What the rule ranks by: the increase in the sum of squared load scores of the nurses involved">Strain cost (lower is better)</th><th></th></tr>`;
  const tags = () => "";
  const rowCls = (o) => (o.rank === 1 ? "top" : "");
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
    html += `<tr class="${focus.has(n.id) ? "focus" : ""}"><th>${n.id}${n.senior ? "*" : ""}</th>`;
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
  $("#ward-kpis").textContent = `Past and next 28 days: load inequality ${k.gini.toFixed(3)} (0 = equal) · top 10% of nurses carry ${(k.top10_qr_share * 100).toFixed(0)}% of quick returns · most quick returns on one nurse: ${k.max_qr}`;
  if (!window.Chart) return;
  const rows = [...state.strain].sort((a, b) => b.strain - a.strain);
  const focus = focusNurses();
  const data = {
    labels: rows.map((r) => r.nurse),
    datasets: [{ label: "Load score (past and next 28 days)", data: rows.map((r) => r.strain),
      backgroundColor: rows.map((r) => (focus.has(r.nurse) ? "#0c2074" : "#86d2ed")) }],
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
  await putPolicy(body, "Policy saved. Options re-ranked.");
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
      const miss = r.not_recorded ? `${NOT_RECORDED} A pre-generated answer exists for the example sentence (press Demo to restore it).` : "GenAI unavailable, no proposal made.";
      $("#translate-result").innerHTML = `<p class="muted" title="${esc(r.error || "")}">${icon("warn")} ${esc(miss)} The current weights stay in force.</p>`;
      return;
    }
    proposal = { weights: r.proposal.weights, text };
    $("#translate-status").innerHTML = `<span class="src">${esc(r.source)} · ${r.latency_ms} ms</span>`;
    const rows = METRICS.map((m) => {
      const cur = r.current[m], nw = r.proposal.weights[m];
      return `<tr><td>${esc(METRIC_LABEL[m])}</td><td>${cur}</td><td class="${cur !== nw ? "changed" : ""}">${nw}</td></tr>`;
    }).join("");
    const changed = METRICS.filter((m) => r.current[m] !== r.proposal.weights[m]);
    const chg = changed.length ? changed.map((m) => `<span class="w">${esc(METRIC_LABEL[m])}: <b>${r.current[m]} → ${r.proposal.weights[m]}</b></span>`).join("")
      : '<span class="w">No weight change proposed</span>';
    $("#translate-result").innerHTML = `<div class="box-head" style="border-radius:8px 8px 0 0">${AI_TAG}Proposed weight change (old → new)</div>` +
      `<div class="box-body"><div class="wchange">${chg}</div><table class="cmp x-expert"><tr><th>Item</th><th>Current</th><th>Proposed</th></tr>${rows}</table>` +
      '<p id="translate-rationale"></p><div><button type="button" id="btn-apply-proposal" class="primary">Approve</button>' +
      '<button type="button" id="btn-discard-proposal">Discard</button> <span class="muted">Nothing changes until you approve.</span></div></div>';
    $("#translate-rationale").textContent = r.proposal.rationale_plain ?? r.proposal.rationale;
    $("#btn-apply-proposal").addEventListener("click", () => guarded(applyProposal));
    $("#btn-discard-proposal").addEventListener("click", discardProposal);
  } finally {
    $("#btn-translate").disabled = false;
    if ($("#translate-status").textContent === "GenAI is translating…") $("#translate-status").textContent = "";
  }
}

const proposalApplied = (w, m) => w[m];

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
  const was = policyForm ? policyForm.weights : null;
  await putPolicy(body, "Proposed weights applied. Options re-ranked.");
  discardProposal();
  const changed = was ? METRICS.filter((m) => was[m] !== proposalApplied(body.weights, m)) : [];
  $("#translate-result").innerHTML = `<div class="approved">${icon("checkCircle")}<div><b>Approved.</b> ` +
    (changed.length ? changed.map((m) => `${esc(METRIC_LABEL[m])}: <b>${was[m]} → ${body.weights[m]}</b>`).join(", ") : "Weights saved") +
    `. The options in step 2 are re-ranked with the new weights.</div></div>`;
}

// ---- Two-page presenter view ------------------------------------------------------------------
let resultsData = null;
let resChart = null;

function pageFromUrl() {
  const q = new URLSearchParams(location.search).get("page");
  if (q === "results" || location.hash === "#results") return "results";
  if (q === "monthly" || location.hash === "#monthly") return "monthly";
  if (q === "one" || location.hash === "#one") return "one";
  try { const p = localStorage.getItem("roster-page"); return p === "results" || p === "monthly" ? p : "one"; } catch (e) { return "one"; }
}

function setPage(p) {
  document.body.classList.toggle("pg-results", p === "results");
  document.body.classList.toggle("pg-monthly", p === "monthly");
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
    $("#res-hero").textContent = `Hospital rule: ${x}% ${ge3.change_pct <= 0 ? "fewer" : "more"} nurses with 3+ quick returns in any 28 days, better on ${ge3.wins} of ${n} wards.`;
  } else $("#res-hero").textContent = "";
  const cell = (side, key) => { if (!side) return '<span class="flat">–</span>'; const d = key === "changes_per_repair" ? 2 : 1;
    return `${fmtNum(side.mean, d)}<span class="rng">(range ${fmtNum(side.min, d)}–${fmtNum(side.max, d)})</span>`; };
  const chg = (m) => { if (m.change_pct === null) return '<span class="flat">–</span>';
    const v = Math.round(m.change_pct);
    return `<span class="${v < 0 ? "good" : v > 0 ? "badc" : "flat"}">${v > 0 ? "+" : v < 0 ? MINUS : ""}${Math.abs(v)}%</span>`; };
  const rows = r.metrics.map((m) => `<tr class="${m.cost ? "cost" : ""}"><td>${esc(m.label)}${m.cost ? ' <span class="tag-cost">(the cost)</span>' : ""}</td>` +
    `<td class="num">${cell(m.baseline, m.key)}</td><td class="num">${cell(m.ours, m.key)}</td><td class="num">${chg(m)}</td>` +
    `<td class="num">${m.ties === n ? `equal in ${n} of ${n}` : `${m.wins} of ${n}${m.ties ? ` <span class="tag-cost">(${m.ties} tied)</span>` : ""}`}</td></tr>`).join("");
  $("#res-table").innerHTML = `<table class="res"><tr><th>Metric</th><th class="num">Today's software</th><th class="num">Hospital rule</th>` +
    `<th class="num">Change</th><th class="num">Wards where the rule is better</th></tr>${rows}</table>`;
  renderResultsChart(r);
  renderResultsKpis(r);
  const e = r.explanations, parts = [];
  if (e && e.design === "e10") {
    parts.push(`GenAI summary shown (passed the check) for <b>${Math.round(e.coverage * 1000) / 10}%</b> of repairs; when flagged, the planner sees the rule's facts only`);
    if (e.hand_sample) parts.push(`hand read of ${e.hand_sample} shown summaries: <b>${e.hand_errors}</b> contain an error (${e.hand_factual} factual, ${e.hand_wording} wording: a call-in described as a move)`);
    if (e.mean_latency_s != null) parts.push(`about <b>${e.mean_latency_s.toFixed(1)} s</b> per summary`);
  } else if (e) {
    if (e.fact_check_pass_rate != null) parts.push(`Fact check passed for <b>${Math.round(e.fact_check_pass_rate * 100)}%</b> of explanations`);
    if (e.direction_error_rate != null) parts.push(`wording direction wrong in <b>${Math.round(e.direction_error_rate * 100)}%</b>`);
    if (e.valid_output_rate != null) parts.push(`valid output <b>${Math.round(e.valid_output_rate * 100)}%</b>`);
    if (e.mean_latency_s != null) parts.push(`about <b>${Math.round(e.mean_latency_s)} s</b> per explanation`);
  }
  $("#res-rel").innerHTML = parts.length ? `<div class="rel-title">How reliable are GenAI's summaries? (${esc(e.model ?? "")}, ${e.n_decisions ?? "?"} decisions)</div>${parts.join('<span class="sep">·</span>')}` +
    '<p class="muted">GenAI never changes the ranking or the choice. If it fails, the rule\'s choice stands.</p>' : "";
  $("#res-rel").classList.toggle("hidden", !parts.length);
  $("#res-foot").textContent = "";
  if (r.model) $("#foot").textContent = `Simulated wards built from Erasmus MC and Dutch parameters · GenAI runs locally (${r.model}) · the hospital rule ranks, the planner decides`;
}

// Headline tiles: one big number per key measure, coloured and worded (benefit / cost / same).
function kpiTile(label, pct, from, to, isCost) {
  const v = pct === null || pct === undefined ? null : Math.round(pct);
  const kind = v === null || v === 0 ? "same" : isCost ? "cost" : v < 0 ? "benefit" : "cost";
  const big = v === null ? "n/a" : v === 0 ? "Same" : `${v > 0 ? "+" : MINUS}${Math.abs(v)}%`;
  const word = kind === "same" ? "no change" : kind === "benefit" ? "benefit" : "the cost";
  return `<div class="kpi ${kind}"><div class="kpi-big">${big}</div><div class="kpi-word">${kind === "benefit" ? icon("check") : kind === "cost" ? icon("warn") : ""}${word}</div>` +
    `<div class="kpi-lbl">${esc(label)}</div><div class="kpi-from">${esc(String(from))} → ${esc(String(to))}</div></div>`;
}

function renderResultsKpis(r) {
  const pick = [["nurses_qr_ge3_28d", "Nurses with 3+ quick returns in any 28 days"], ["QR_total", "Quick returns per ward"],
    ["unfilled", "Unfilled shifts"], ["SN_total", "Short-notice changes"]];
  $("#res-kpis").innerHTML = pick.map(([k, l]) => { const m = r.metrics.find((x) => x.key === k); if (!m || !m.baseline || !m.ours) return "";
    return kpiTile(l, m.change_pct, fmtNum(m.baseline.mean, 1), fmtNum(m.ours.mean, 1), m.cost); }).join("");
}

function renderResultsChart(r) {
  // Benefits in green (lower is better), costs in red (the price of the benefit).
  const keys = ["QR_total", "nurses_qr_ge3_28d", "max_qr", "SN_total", "changes_per_repair"];
  const names = { QR_total: ["Quick returns"], nurses_qr_ge3_28d: ["Nurses with 3+", "quick returns"], max_qr: ["Most quick returns", "for one nurse"],
    SN_total: ["Short-notice changes", "(cost)"], changes_per_repair: ["Shifts changed per", "sick call (cost)"] };
  const ms = keys.map((k) => r.metrics.find((m) => m.key === k)).filter(Boolean);
  const avg = ms.map((m) => (m.change_pct === null ? null : Number(m.change_pct.toFixed(1))));
  const colors = ms.map((m) => (m.cost ? "#b42318" : "#1a7f4e"));
  $("#res-cap").textContent = "Hospital rule vs today's software, average change across all wards. Green: benefits, below zero means fewer. Red: costs, above zero means more.";
  if (!window.Chart) return;
  const data = { labels: ms.map((m) => names[m.key]), datasets: [
    { label: "Average of all wards (green = benefit, red = cost)", data: avg, backgroundColor: colors }] };
  if (resChart) { resChart.destroy(); resChart = null; }
  resChart = new Chart($("#res-chart"), { type: "bar", data, options: { animation: false, maintainAspectRatio: false,
    plugins: { legend: { display: false }, title: { display: true, text: "Change vs today's software (%)", color: "#0c2074", font: { size: 15 } },
      tooltip: { callbacks: { label: (c) => `${c.parsed.y > 0 ? "+" : ""}${c.parsed.y}%` } } },
    scales: { y: { suggestedMin: -100, suggestedMax: 100, ticks: { callback: (v) => `${v > 0 ? "+" : ""}${v}%`, color: "#0c2074", font: { size: 14 } }, grid: { color: "#dfe3ec" } },
      x: { ticks: { color: "#0c2074", font: { size: 14 }, maxRotation: 0, minRotation: 0 }, grid: { color: "#dfe3ec" } } } },
    plugins: [{ id: "barLabels", afterDatasetsDraw(ch) { const { ctx } = ch; ctx.save(); ctx.font = "bold 14px Helvetica Neue, Arial, sans-serif"; ctx.textAlign = "center";
      ch.getDatasetMeta(0).data.forEach((bar, i) => { const v = avg[i]; if (v === null) return; const cost = ms[i].cost;
        ctx.fillStyle = cost ? "#b42318" : "#1a7f4e";
        ctx.fillText(`${v > 0 ? "+" : MINUS}${Math.abs(Math.round(v))}% ${cost ? "cost" : "benefit"}`, bar.x, v < 0 ? bar.y + 18 : bar.y - 6); }); ctx.restore(); } }] });
}

// ---- Monthly report: rules compute the facts, GenAI writes the text, the checker verifies it ---------
const MR_ROWS = [["Quick returns", "quick_returns"], ["Nurses with 3+ quick returns", "nurses_3plus_quick_returns"],
  ["Most quick returns for one nurse", "max_quick_returns_one_nurse"], ["Unfilled shifts", "unfilled_shifts"],
  ["Short-notice changes (the cost)", "last_minute_call_ins"], ["Shift changes per sick call (the cost)", "shift_changes_per_sick_call"],
  ["Nurses whose shifts changed", "nurses_whose_shifts_changed"]];

function renderMonthlyFacts(f) {
  const r = f.hospital_rule, o = f.todays_software;
  const rows = MR_ROWS.map(([l, k]) => { const [cx, cy] = cmpClass(o[k], r[k]);
    const v = (cls, x) => (cls ? `${icon("check")} ${x}` : x);
    return `<tr><td>${l}</td><td class="num ${cx}">${v(cx, o[k])}</td><td class="num ${cy}">${v(cy, r[k])}</td></tr>`; }).join("");
  const nurses = (xs, k) => xs.length ? xs.map((x) => `${esc(niceNurse(x.nurse))} (${x[k]})`).join(", ") : "none";
  const p = f.planner, g = f.genai_explanations;
  const planner = p ? `${p.decisions_by_planner} decision${p.decisions_by_planner === 1 ? "" : "s"} in the live demo: ${p.accepted_rule_choice} accepted, ${p.overridden} overridden` +
    (Object.keys(p.override_reasons).length ? ` (${Object.entries(p.override_reasons).map(([k, v]) => `${esc(k)}: ${v}`).join(", ")})` : "") : "n/a";
  return `<p>Ward ${f.ward} · days ${esc(f.days)} · ${f.sick_calls} sick calls · same sick calls for both</p>` +
    `<p class="muted">Simulated month: the rule's choice applied to every sick call. Planner overrides from the live log are counted below but not reflected in these roster numbers.</p>` +
    `<table class="cmp"><tr><th></th><th>Today's software</th><th>Hospital rule</th></tr>${rows}</table>` +
    `<ul><li>Quick returns in the original roster for the same days, before any sick call: <b>${f.quick_returns_in_original_roster}</b> (some disappear when a sick nurse's shift is removed)</li>` +
    `<li>Most short-notice changes: ${nurses(f.most_last_minute_call_ins, "last_minute_call_ins")}</li>` +
    `<li>Most quick returns: ${nurses(f.most_quick_returns, "quick_returns")}</li>` +
    `<li>Planner: ${planner}</li>` +
    (g ? `<li>GenAI summaries (measured run): ${g.passed_fact_check} of ${g.explained} passed the check and were shown</li>` : "") + "</ul>";
}

async function writeMonthly() {
  const month = Number($("#mr-month").value) || 1;
  $("#btn-monthly").disabled = true;
  $("#mr-status").innerHTML = '<span class="spinner"></span>Computing facts and asking GenAI to write…';
  $("#mr-text").innerHTML = ""; $("#mr-facts").innerHTML = ""; $("#mr-kpis").innerHTML = "";
  try {
    const r = await api("/api/monthly-report", { method: "POST", body: JSON.stringify({ month }) });
    $("#mr-facts").innerHTML = renderMonthlyFacts(r.facts);
    { const f = r.facts, pc = f.pct_change || {}, o = f.todays_software, h = f.hospital_rule;
      $("#mr-kpis").innerHTML = kpiTile("Quick returns this month", pc.quick_returns, o.quick_returns, h.quick_returns, false) +
        kpiTile("Nurses with 3+ quick returns", pc.nurses_3plus_quick_returns, o.nurses_3plus_quick_returns, h.nurses_3plus_quick_returns, false) +
        kpiTile("Short-notice changes", pc.last_minute_call_ins, o.last_minute_call_ins, h.last_minute_call_ins, true); }
    if (!r.report) {
      $("#mr-text").innerHTML = `<p class="muted" title="${esc(r.error || "")}">${icon("warn")} ${esc(genaiMissText(r, "GenAI unavailable, facts shown."))} The table on the left is complete and computed without GenAI.</p>`;
    } else {
      const c = r.check, issues = [];
      if (c.unsupported_numbers.length) issues.push(`Numbers not in the facts: ${c.unsupported_numbers.join(", ")}`);
      if (c.direction_errors.length) issues.push(`Wording says the opposite of the numbers: ${c.direction_errors.join(", ")}`);
      if (c.nurse_errors.length) issues.push(`Wrong number for a nurse: ${c.nurse_errors.join("; ")}`);
      (c.fact_block_errors || []).forEach((x) => issues.push(x));
      (c.policy_claim_errors || []).forEach((x) => issues.push(x));
      $("#mr-text").innerHTML = c.verified
        ? `<p>${esc(niceNurse(r.report.summary))}</p><b>For the review meeting</b><ol>` +
          r.report.discussion_points.map((x) => `<li>${esc(niceNurse(x))}</li>`).join("") + "</ol>" +
          `${factsBadge(true, true)}` + ' <span class="badge warn-badge">A person reads it before sharing: the check cannot see every wrong statement</span>'
        : `<p class="muted">GenAI's text is hidden because the check flagged it. The table on the left is complete.</p>` +
          `<ul>${issues.map((i) => `<li class="warn">${esc(niceNurse(i))}</li>`).join("")}</ul>`;
    }
    $("#mr-status").innerHTML = `<span class="src">${esc(r.source)} · ${Math.round(r.latency_ms / 100) / 10} s</span>`;
  } catch (e) {
    $("#mr-status").textContent = `Report failed: ${e.message}`;
  } finally {
    $("#btn-monthly").disabled = false;
    await loadAudit();
  }
}

// ---- GenAI autoplay --------------------------------------------------------------------------
const BUSY_SELECTORS = "#btn-start, #btn-view, #btn-new, #btn-next, #btn-ff, #btn-auto, #btn-autoplay, #auto-n, #policy-form button, #btn-apply-proposal, #btn-translate, #btn-override-main, .mode";
const WHO = { strain: "the hospital rule", baseline: "today's software" };

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
    line.textContent = niceNurse(`Sick call: ${it.absent}, ${String(it.shift).toLowerCase()} shift, day ${it.day} → ${by}: ${it.description ?? it.chosen_change_text}`);
  } else {
    const nurse = it.chosen_nurse ? `${it.chosen_nurse} (${it.chosen})` : it.chosen;
    const by = String(it.by).replace(/^Formula/, RULE).replace(/^ORTEC-like/, "Today's software");
    line.textContent = `Sick call: ${it.absent}, ${String(it.shift).toLowerCase()} shift, day ${it.day} → ${by} gave it to ${nurse}. `;
    const verdict = document.createElement("span");
    verdict.textContent = it.agrees_with_formula ? "Same as hospital rule check" : `Differs: hospital rule check preferred ${it.formula_top}`;
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
  const line = (r) => r.mode === "monthly_report"
    ? `<tr><td>${esc(r.ts.slice(11, 19))}</td><td></td><td>Monthly report</td><td>month ${r.month}</td><td></td><td></td><td>${esc(r.source ?? "")} · ${esc(r.report_status ?? "")}</td></tr>`
    : r.mode === "policy"
    ? `<tr><td>${esc(r.ts.slice(11, 19))}</td><td></td><td>Policy</td><td>weights updated (${esc(r.source ?? "manual")})</td><td></td><td></td><td>${esc(r.policy_text ?? "")}</td></tr>`
    : `<tr><td>${esc(r.ts.slice(11, 19))}</td><td>${r.event_id}</td><td>${esc(MODE_LABEL[r.mode] ?? r.mode)}${r.fallback ? " (fallback)" : ""}</td>` +
      `<td>${esc(r.option_id ?? "unfilled")}</td><td>${esc(r.top_option ?? "")}</td><td>${esc(r.override_reason ?? "")}</td>` +
      `<td>${esc(r.explanation_source ?? "")}${r.verified === false ? " (flagged)" : ""}</td></tr>`;
  $("#audit").innerHTML = "<tr><th>Time</th><th>Sick call</th><th>Mode</th><th>Chosen</th><th>Top</th><th>Override</th><th>Explanation</th></tr>" +
    rows.map(line).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  // Screenshot mode (?shot=1): fixed 1400 px width, no setup / view controls, page ends at its last card.
  // 2x pixel density is set by the capture (device scale factor 2); CSS cannot change it.
  if (new URLSearchParams(location.search).get("shot") === "1") document.body.classList.add("shot");
  document.querySelectorAll("[data-icon]").forEach((el) => { el.outerHTML = icon(el.dataset.icon); });
  $("#btn-start").addEventListener("click", () => guarded(startPresenter));
  $("#btn-demo").addEventListener("click", () => guarded(startDemo));
  $("#btn-apply-main").addEventListener("click", () => guarded(applyMain));
  $("#btn-override-main").addEventListener("click", () => guarded(overrideMain));
  $("#btn-monthly").addEventListener("click", () => guarded(writeMonthly));
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
    await setView(storedView());
    await setMode("strain");
    render();
    await loadAudit();
    if (state.autoplay_running) watchAutoplay();
    if (new URLSearchParams(location.search).get("demo") === "1") await startDemo();
    await llmStatus();
  });
});
