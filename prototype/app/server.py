"""Planner web app API (spec §5). One in-memory scenario at a time."""
from __future__ import annotations

import csv
import json
import math
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from llm.monthly import compute_month_facts, write_report
from llm.plain import plainify, replace_option_ids, shift_words
from llm.policy_translate import translate_policy
from llm.prompt import build_explain_payload
from llm.service import explain_decision
from sim.compare import (card_lines, difference_text, pick_summary, plain_change, plain_words, rest_effect, rest_lines,
                         ward_context, who_words)
from sim.engine import Scenario, run_scenario
from sim.metrics import gini, plan_scoreboard, run_metrics, top_share
from sim.policies import (describe, generate_candidates, period_hours, rank_options,
                          score_options, ward_strains)
from sim.strain import nurse_metrics, strain, window
from sim.ward import load_json

APP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = APP_DIR.parent / "results"
AUDIT_PATH = Path(os.environ.get("ROSTER_AUDIT_PATH", APP_DIR / "data" / "audit.jsonl"))
Mode = Literal["baseline", "strain"]
Reason = Literal["local_knowledge", "preference", "skill_mix", "other"]


PREVIEW_KEYS = ("QR_total", "nurses_qr_ge3_28d", "max_qr", "gini_strain", "unfilled", "SN_total",
                "changes_per_repair")

RESULT_METRICS = (("QR_total", "Quick returns per ward (8 weeks)", False),
                  ("nurses_qr_ge3_28d", "Nurses with 3+ quick returns in 4 weeks", False),
                  ("max_qr", "Most quick returns for one nurse", False),
                  ("unfilled", "Unfilled shifts", False),
                  ("SN_total", "Last-minute call-ins", True),
                  ("changes_per_repair", "Shifts changed per sick call", True))

def _read_rows(name: str, value: str, col: str = "policy") -> list[dict]:
    with (RESULTS_DIR / name).open(newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get(col) == value]

def _per_seed(rows: list[dict]) -> dict[int, dict]:
    """Mean RESULT_METRICS per seed over rows whose metrics are all finite (others are skipped)."""
    acc: dict[int, list[dict]] = {}
    for r in rows:
        try:
            seed = int(float(r["seed"]))
            vals = {k: float(r[k]) for k, _, _ in RESULT_METRICS}
        except (KeyError, ValueError, TypeError):
            continue
        if all(math.isfinite(v) for v in vals.values()):
            acc.setdefault(seed, []).append(vals)
    return {sd: {k: sum(v[k] for v in vs) / len(vs) for k in vs[0]} for sd, vs in acc.items()}

def _finite_mean(rows: list[dict], key: str) -> float | None:
    vals = []
    for r in rows:
        try:
            v = float(r[key])
        except (KeyError, ValueError, TypeError):
            continue
        if math.isfinite(v):
            vals.append(v)
    return sum(vals) / len(vals) if vals else None

def _explanation_reliability(model: str | None) -> dict | None:
    """Arm B explanation quality for the app's model from results/e6_explanations_summary.csv."""
    try:
        with (RESULTS_DIR / "e6_explanations_summary.csv").open(newline="") as fh:
            rows = list(csv.DictReader(fh))
    except (OSError, csv.Error):
        return None
    row = next((r for r in rows if r.get("model") == model), rows[0] if rows else None)
    if row is None:
        return None
    out = {"model": row.get("model"), "n_decisions": None}
    for k in ("valid_output_rate", "fact_check_pass_rate", "direction_error_rate", "mean_latency_s", "n_decisions"):
        try:
            v = float(row[k])
            out[k] = v if math.isfinite(v) else None
        except (KeyError, ValueError, TypeError):
            out[k] = None
    return out

def load_results() -> dict | None:
    """E6 arms per ward: A (ORTEC-like) and B (rule-ranked).

    Reads results/e6_runs.csv; None if unusable. 'wins' counts wards where B beats A."""
    try:
        base = _per_seed(_read_rows("e6_runs.csv", "A", "arm"))
        ours = _per_seed(_read_rows("e6_runs.csv", "B", "arm"))
        seeds = sorted(set(ours) & set(base))
        if not seeds:
            return None
        side = lambda xs: {"mean": sum(xs) / len(xs), "min": min(xs), "max": max(xs)}  # noqa: E731
        metrics = []
        for key, label, cost in RESULT_METRICS:
            b, o = [base[sd][key] for sd in seeds], [ours[sd][key] for sd in seeds]
            sb, so = side(b), side(o)
            metrics.append({"key": key, "label": label, "cost": cost, "baseline": sb, "ours": so,
                            "change_pct": 100 * (so["mean"] - sb["mean"]) / sb["mean"] if sb["mean"] > 0 else None,
                            "wins": sum(1 for x, y in zip(o, b) if x < y),
                            "ties": sum(1 for x, y in zip(o, b) if x == y)})
        wards = [{"ward": i + 1, "seed": sd,
                  "values": {k: {"baseline": base[sd][k], "ours": ours[sd][k]} for k, _, _ in RESULT_METRICS}}
                 for i, sd in enumerate(seeds)]
        model = load_json("policy.json").get("model")
        return {"available": True, "n_wards": len(seeds), "metrics": metrics,
                "wards": wards, "model": model, "explanations": _explanation_reliability(model)}
    except (OSError, ValueError, KeyError, TypeError, csv.Error):
        return None

class AppState:
    def __init__(self) -> None:
        self.policy = load_json("policy.json")
        self.reset(0)

    def compute_preview(self) -> None:
        weights = self.policy["weights"]
        seed = self.scenario.seed
        out = {}
        for name in ("baseline", "strain"):
            m = run_metrics(run_scenario(seed, name, self.policy), weights)
            out[name] = {k: (round(m[k], 3) if isinstance(m[k], float) else m[k]) for k in PREVIEW_KEYS}
        self.preview = out

    def mark_start(self) -> None:
        """Common starting point of both chart lines (the plan before the first counted sick call)."""
        sb = plan_scoreboard(self.scenario.roster, self.scenario.ward, self.policy["weights"])
        self.history_start = {"qr": sb["quick_returns"], "ge3": sb["nurses_qr_ge3_28d"]}
        self.takeover = {"ours": sb, "ortec": plan_scoreboard(self.shadow.roster, self.shadow.ward,
                                                              self.policy["weights"])}

    def reset(self, seed: int) -> None:
        self.scenario = Scenario(seed)
        self.ctx = None
        self.options = []
        self.scored = []
        self.explanation = None
        self.policy_text = None
        self.last_day = 0
        self.shadow = Scenario(seed)
        self.shadow_pending = None  # shadow event opened early (fair start), resolved by the next sync
        self.history = []
        self.mark_start()
        self.autoplay_log = []
        self.compute_preview()


STATE = AppState()
STATE_LOCK = threading.RLock()
SHIFT_NAMES = {"D": "day", "E": "evening", "N": "night"}
AUTO: dict = {}


def _auto_reset() -> None:
    AUTO.clear()
    AUTO.update({"running": False, "done": 0, "total": 0, "error": None, "cancel": False})


_auto_reset()


def _guard_auto() -> None:
    """Call with STATE_LOCK held: state-mutating endpoints are refused while autoplay runs."""
    if AUTO["running"]:
        raise HTTPException(status_code=409, detail="Autoplay running")
app = FastAPI(title="Roster repair: rule ranks, GenAI explains, planner decides")


class ScenarioIn(BaseModel):
    seed: int = Field(default=0, ge=0)


class ApplyIn(BaseModel):
    event_id: int
    option_id: str
    mode: Mode
    override_reason: Reason | None = None


class WeightsIn(BaseModel):
    QR: float = Field(ge=0)
    N: float = Field(ge=0)
    LR: float = Field(ge=0)
    OT: float = Field(ge=0)
    SN: float = Field(ge=0)


class PolicyIn(BaseModel):
    weights: WeightsIn
    forward_days: int = Field(ge=1, le=28)
    squared: bool = True
    source: Literal["manual", "genai"] = "manual"
    policy_text: str | None = Field(default=None, max_length=1000)


class MonthlyIn(BaseModel):
    month: int = Field(ge=1, le=2)


class TranslateIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class AutoplayIn(BaseModel):
    events: int = Field(ge=1, le=30)
    mode: Mode = "strain"


class FastForwardIn(BaseModel):
    to_day: int | None = Field(default=None, ge=1)
    events: int | None = Field(default=None, ge=1, le=200)
    mode: Mode = "strain"
    reset_history: bool = False


def _append_audit(entry: dict) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "seed": STATE.scenario.seed, **entry}
    with AUDIT_PATH.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def _shadow_resolve(ctx) -> None:
    scored = score_options(ctx, generate_candidates(ctx), STATE.policy)
    if scored:
        STATE.shadow.apply(ctx, rank_options(scored, "baseline")[0].option)
    else:
        STATE.shadow.mark_unfilled(ctx)


def sync_shadow(upto_event_id: int) -> None:
    """Let the ORTEC-like autopilot (baseline top, same ward) resolve every event up to this id."""
    sh = STATE.shadow
    pend = STATE.shadow_pending
    if pend is not None and pend.event_id <= upto_event_id:
        STATE.shadow_pending = None
        _shadow_resolve(pend)
    while (nxt := sh.peek_event_id()) is not None and nxt <= upto_event_id:
        ctx = sh.next_context(upto_event_id)
        if ctx is None:
            break
        _shadow_resolve(ctx)

def _since(now: dict, then: dict) -> dict:
    return {"quick_returns_avoided": then["quick_returns"] - now["quick_returns"],
            "quick_returns_change": now["quick_returns"] - then["quick_returns"],
            "extra_late_calls": now["short_notice_calls"] - then["short_notice_calls"],
            "nurses_3plus_change": now["nurses_qr_ge3_28d"] - then["nurses_qr_ge3_28d"]}

def _since_takeover(ours: dict, ortec: dict) -> dict:
    return {"ours": _since(ours, STATE.takeover["ours"]), "ortec": _since(ortec, STATE.takeover["ortec"]),
            "calls_handled": len(STATE.history)}

def _record_resolved(event_id: int) -> None:
    sync_shadow(event_id)
    w = STATE.policy["weights"]
    ours = plan_scoreboard(STATE.scenario.roster, STATE.scenario.ward, w)
    ortec = plan_scoreboard(STATE.shadow.roster, STATE.shadow.ward, w)
    so, sr = _since(ours, STATE.takeover["ours"]), _since(ortec, STATE.takeover["ortec"])
    STATE.history.append({"n": len(STATE.history) + 1, "ours_qr": ours["quick_returns"],
                          "ortec_qr": ortec["quick_returns"], "ours_ge3": ours["nurses_qr_ge3_28d"],
                          "ortec_ge3": ortec["nurses_qr_ge3_28d"],
                          "ours_avoided": so["quick_returns_avoided"], "ortec_avoided": sr["quick_returns_avoided"],
                          "ours_extra_calls": so["extra_late_calls"], "ortec_extra_calls": sr["extra_late_calls"],
                          "ours_ge3_change": so["nurses_3plus_change"], "ortec_ge3_change": sr["nurses_3plus_change"]})

def _event_json(ctx, unfilled: bool = False) -> dict:
    return {"event_id": ctx.event_id, "absent": ctx.absent, "day": ctx.day, "shift": ctx.shift,
            "notice_h": round(ctx.notice_h, 1), "unfilled": unfilled}


def _state_json(event: dict | None = None) -> dict:
    sc, policy = STATE.scenario, STATE.policy
    ward, roster = sc.ward, sc.roster
    lo, hi = window(STATE.last_day, ward.days, policy["back_days"], policy["forward_days"])
    per = {n.id: nurse_metrics(roster, n.id, lo, hi) for n in ward.nurses}
    strains = {nid: strain(m, policy["weights"]) for nid, m in per.items()}
    qr = [m["QR"] for m in per.values()]
    if event is None and STATE.ctx is not None:
        event = _event_json(STATE.ctx)
    sb_ours = plan_scoreboard(roster, ward, policy["weights"])
    sb_ortec = plan_scoreboard(STATE.shadow.roster, STATE.shadow.ward, policy["weights"])
    return {
        "seed": sc.seed,
        "days": ward.days,
        "nurses": [{"id": n.id, "fte": n.fte, "senior": n.senior, "night_ok": n.night_ok}
                   for n in ward.nurses],
        "grid": roster.by_nurse,
        "changed": sorted(roster.added),
        "absent": sorted(b for b in sc.blocked if b not in ward.leave),
        "leave": sorted(ward.leave),
        "event": event,
        "remaining_events": sc.remaining,
        "unfilled": sc.unfilled,
        "strain": [{"nurse": nid, "strain": round(s, 2), "QR": per[nid]["QR"]} for nid, s in strains.items()],
        "preview": STATE.preview,
        "scoreboard": {"ours": sb_ours, "ortec": sb_ortec,
                       "history": STATE.history, "start": STATE.history_start},
        "since_takeover": _since_takeover(sb_ours, sb_ortec),
        "autoplay_running": bool(AUTO["running"]),
        "kpis": {"gini": round(gini(strains.values()), 3), "top10_qr_share": round(top_share(qr), 3),
                 "max_qr": max(qr) if qr else 0},
    }


def _option_json(so, mode: str) -> dict:
    opt = so.option
    if mode == "baseline":
        nurse = opt.extra_nurse
        return {"id": opt.id, "rank": so.rank_baseline, "kind": opt.kind, "change_text": describe(opt),
                "description": plain_change(opt),
                "nurse": nurse, "contract_h": STATE.scenario.ward.nurse(nurse).weekly_hours,
                "hours_period": period_hours(STATE.scenario.roster, nurse, STATE.ctx.day),
                "n_changes": opt.n_changes}
    return {"id": opt.id, "rank": so.rank_strain, "rank_baseline": so.rank_baseline, "kind": opt.kind,
            "change_text": describe(opt), "description": plain_change(opt), "n_changes": opt.n_changes, "delta_strain": so.delta_strain,
            "nurses": so.nurses}


def _comparison(ours_so, ortec_so, **extra) -> dict:
    ours, ortec = pick_summary(ours_so), pick_summary(ortec_so)
    words = plain_words(ours_so, ortec_so)
    descs = {ours["id"]: ours["description"], ortec["id"]: ortec["description"]}
    wc = ward_context(ward_strains(STATE.ctx, STATE.policy)) if STATE.ctx is not None else None
    rest = ({"ours": rest_lines(STATE.ctx.roster, ours_so.option), "ortec": rest_lines(STATE.ctx.roster, ortec_so.option)}
            if STATE.ctx is not None else None)
    cl = card_lines(ours, ortec, wc, rest)
    fx = ({"ours": rest_effect(STATE.ctx.roster, ours_so.option.changes), "ortec": rest_effect(STATE.ctx.roster, ortec_so.option.changes)}
          if STATE.ctx is not None else None)
    return {"ours": ours, "ortec": ortec, "plain_words": words, "difference": difference_text(ours, ortec, fx, wc),
            "who_words": who_words(ours, ortec, wc) or replace_option_ids(words, descs),
            "card_lines": cl, "rest_lines": cl["rest_lines"], **extra}


def _require_event() -> None:
    if STATE.ctx is None:
        raise HTTPException(status_code=409, detail="No open event")


@app.get("/api/results")
def get_results() -> dict:
    """Results across all measured wards for the presenter's second page (read-only CSVs, no LLM)."""
    return load_results() or {"available": False}

@app.post("/api/scenario")
def new_scenario(body: ScenarioIn) -> dict:
    with STATE_LOCK:
        _guard_auto()
        STATE.reset(body.seed)
        _auto_reset()
        return _state_json()


@app.get("/api/state")
def get_state() -> dict:
    with STATE_LOCK:
        return _state_json()


def _begin(ctx) -> bool:
    """Open ctx for the planner; returns False (and marks it unfilled) if no option exists."""
    STATE.last_day = ctx.day
    options = generate_candidates(ctx)
    if not options:
        STATE.scenario.mark_unfilled(ctx)
        _append_audit({"event_id": ctx.event_id, "day": ctx.day, "shift": ctx.shift,
                       "absent": ctx.absent, "mode": "-", "option_id": None, "unfilled": True})
        _record_resolved(ctx.event_id)
        return False
    STATE.ctx, STATE.options, STATE.explanation = ctx, options, None
    STATE.scored = score_options(ctx, options, STATE.policy)
    return True

@app.post("/api/next-event")
def next_event() -> dict:
    with STATE_LOCK:
        _guard_auto()
        if STATE.ctx is not None:
            raise HTTPException(status_code=409, detail="Resolve the current event first")
        ctx = STATE.scenario.next_context()
        if ctx is None:
            sync_shadow(10**9)
            return {"done": True, "state": _state_json()}
        if not _begin(ctx):
            return {"done": False, "state": _state_json(event=_event_json(ctx, unfilled=True))}
        return {"done": False, "state": _state_json()}

def _clear_event() -> None:
    STATE.ctx, STATE.options, STATE.scored = None, [], []
    STATE.explanation = None

def _auto_entry(ctx, top, policy_name: str) -> dict:
    return {"event_id": ctx.event_id, "day": ctx.day, "shift": ctx.shift, "absent": ctx.absent,
            "mode": "auto", "option_id": top.option.id if top else None, "rank": 1 if top else None,
            "top_option": top.option.id if top else None, "override_reason": None,
            "explanation_source": None, "verified": None, "policy": policy_name,
            **({} if top else {"unfilled": True})}

def _auto_resolve(ctx, policy_name: str) -> None:
    STATE.last_day = ctx.day
    options = generate_candidates(ctx)
    top = rank_options(score_options(ctx, options, STATE.policy), policy_name)[0] if options else None
    if top is None:
        STATE.scenario.mark_unfilled(ctx)
    else:
        STATE.scenario.apply(ctx, top.option)
    _append_audit(_auto_entry(ctx, top, policy_name))
    _record_resolved(ctx.event_id)

@app.post("/api/fast-forward")
def fast_forward(body: FastForwardIn) -> dict:
    with STATE_LOCK:
        _guard_auto()
        if (body.to_day is None) == (body.events is None):
            raise HTTPException(status_code=422, detail="Provide exactly one of to_day or events")
        if body.to_day is not None and body.to_day > STATE.scenario.ward.days:
            raise HTTPException(status_code=422, detail="to_day is beyond the horizon")
        # never calls the LLM; a fair start (reset_history) is always today's software
        policy_name = "baseline" if body.mode == "baseline" or body.reset_history else "strain"
        resolved = resolved_open = 0
        if STATE.ctx is not None:
            ctx = STATE.ctx
            top = rank_options(STATE.scored, policy_name)[0]
            STATE.scenario.apply(ctx, top.option)
            _append_audit(_auto_entry(ctx, top, policy_name))
            _record_resolved(ctx.event_id)
            _clear_event()
            resolved_open = 1
        stopping = False
        while True:
            ctx = STATE.scenario.next_context()
            if ctx is None:
                sync_shadow(10**9)
                break
            if not stopping:
                stopping = (body.events is not None and resolved >= body.events) or \
                           (body.to_day is not None and ctx.reveal_time >= (body.to_day - 1) * 24)
            if stopping:
                if _begin(ctx):
                    break
                resolved += 1  # unfilled: resolved by _begin, keep looking for an openable event
                continue
            _auto_resolve(ctx, policy_name)
            resolved += 1
        if body.reset_history:
            STATE.history = []  # fair start: the scoreboard counts from here
            if STATE.ctx is not None and STATE.shadow_pending is None:
                # the open event already left a gap in our roster; open it on the shadow too
                STATE.shadow_pending = STATE.shadow.next_context(STATE.ctx.event_id)
            STATE.mark_start()
        return {"resolved": resolved, "resolved_open": resolved_open, "state": _state_json()}

@app.get("/api/options")
def get_options(mode: Mode = "baseline", limit: int = Query(10, ge=1, le=200)) -> dict:
    with STATE_LOCK:
        _require_event()
        ranked = rank_options(STATE.scored, mode)[:limit]
        ours = rank_options(STATE.scored, "strain")[0]
        ortec = rank_options(STATE.scored, "baseline")[0]
        comparison = _comparison(ours, ortec)
        return {"mode": mode, "options": [_option_json(so, mode) for so in ranked], "comparison": comparison}


@app.post("/api/explain")
def explain_current() -> dict:
    with STATE_LOCK:  # snapshot under the lock, call the LLM outside it
        _guard_auto()
        _require_event()
        ctx = STATE.ctx
        if len(STATE.scored) < 1:
            raise HTTPException(status_code=409, detail="No options to explain")
        payload = build_explain_payload(ctx, STATE.scored, STATE.policy, STATE.policy_text)
        model, timeout = STATE.policy.get("model", "qwen3:8b"), STATE.policy.get("ui_timeout_s", 30)
    result = explain_decision(payload, model, timeout)  # explains the rule's choice; never changes it
    with STATE_LOCK:
        if STATE.ctx is ctx:
            STATE.explanation = result
    return {**result, "event_id": ctx.event_id}


@app.post("/api/apply")
def apply_option(body: ApplyIn) -> dict:
    with STATE_LOCK:
        _guard_auto()
        return _apply_locked(body)


def _apply_locked(body: ApplyIn) -> dict:
    _require_event()
    if body.event_id != STATE.ctx.event_id:
        raise HTTPException(status_code=409, detail="Event mismatch: option is stale")
    match = next((so for so in STATE.scored if so.option.id == body.option_id), None)
    if match is None:
        raise HTTPException(status_code=409, detail="Option is not part of the current event")
    formula_top = rank_options(STATE.scored, "strain")[0].option.id
    if body.mode == "baseline":
        rank, top = match.rank_baseline, rank_options(STATE.scored, "baseline")[0].option.id
    else:
        rank, top = match.rank_strain, formula_top
    if rank != 1 and body.override_reason is None:
        raise HTTPException(status_code=422, detail="override_reason is required for a non-top option")
    ctx = STATE.ctx
    STATE.scenario.apply(ctx, match.option)
    _record_resolved(ctx.event_id)
    expl = STATE.explanation if body.mode == "strain" else None
    entry = {
        "event_id": ctx.event_id, "day": ctx.day, "shift": ctx.shift, "absent": ctx.absent,
        "mode": body.mode, "option_id": match.option.id, "rank": rank,
        "top_option": top,
        "override_reason": body.override_reason,
        "explanation_source": expl["source"] if expl else None,
        "verified": expl["check"]["verified"] if expl else None,
    }
    if body.mode == "strain":
        entry.update({
            "ranking": [so.option.id for so in rank_options(STATE.scored, "strain")[:5]],
            "ortec_choice": rank_options(STATE.scored, "baseline")[0].option.id,
            "accepted_top": rank == 1,
            "explanation_status": expl["check"]["status"] if expl else "not ready",
            "explanation_text": expl["display_text"] if expl else None,
            "explanation_error": expl["error"] if expl else None,
            "policy_text": STATE.policy_text,
        })
    _append_audit(entry)
    _clear_event()
    return {"state": _state_json()}


@app.get("/api/policy")
def get_policy() -> dict:
    return STATE.policy


@app.post("/api/policy/translate")
def translate(body: TranslateIn) -> dict:
    """Propose weights from words. Read-only: the policy is only changed by PUT /api/policy."""
    current = dict(STATE.policy["weights"])
    result = translate_policy(body.text, current, STATE.policy.get("model", "qwen3:8b"), 45)
    if result.get("proposal"):
        result["proposal"]["rationale_plain"] = plainify(result["proposal"].get("rationale"))
    return {**result, "current": current}


@app.put("/api/policy")
def put_policy(body: PolicyIn) -> dict:
    with STATE_LOCK:
        _guard_auto()
        STATE.policy = {**STATE.policy, "weights": body.weights.model_dump(),
                        "forward_days": body.forward_days, "squared": body.squared}
        if body.policy_text:
            STATE.policy_text = body.policy_text  # the explanation cites the approved policy
        _append_audit({"mode": "policy", "source": body.source, "policy_text": body.policy_text,
                       "weights": STATE.policy["weights"], "forward_days": body.forward_days,
                       "squared": body.squared})
        if STATE.ctx is not None:
            STATE.scored = score_options(STATE.ctx, STATE.options, STATE.policy)
            STATE.explanation = None
        STATE.compute_preview()
        return STATE.policy


def _open_next_event() -> bool:
    """Open the next fillable event (unfilled ones are resolved on the way). False when none is left."""
    while True:
        ctx = STATE.scenario.next_context()
        if ctx is None:
            sync_shadow(10**9)
            return False
        if _begin(ctx):
            return True


def _autoplay_status() -> dict:
    return {"running": AUTO["running"], "done": AUTO["done"], "total": AUTO["total"],
            "error": AUTO["error"], "log": list(STATE.autoplay_log[-30:])}


def _autoplay_step(mode: str) -> bool:
    """Resolve one event (the open one first, else the next). False when the run should stop."""
    with STATE_LOCK:
        if STATE.ctx is None and not _open_next_event():
            return False
        ctx = STATE.ctx
        formula_so = rank_options(STATE.scored, "strain")[0]
        ortec_so = rank_options(STATE.scored, "baseline")[0]
        if mode == "baseline":
            chosen_so, by, text = ortec_so, "ORTEC-like", "Picked by the ORTEC-like rule: fewest changes first."
        else:
            chosen_so, by, text = formula_so, "Formula", "Picked by the load formula: protect the most-loaded nurses."
        chosen = chosen_so.option.id
        option_texts = {so.option.id: plain_change(so.option) for so in STATE.scored}
        STATE.last_day = ctx.day
        STATE.scenario.apply(ctx, chosen_so.option)
        top = ortec_so if mode == "baseline" else formula_so
        entry = {
            "event_id": ctx.event_id, "day": ctx.day, "shift": ctx.shift, "absent": ctx.absent,
            "mode": f"auto-{mode}", "option_id": chosen,
            "rank": 1 if chosen == top.option.id else max(chosen_so.rank_strain, 2),
            "top_option": top.option.id, "override_reason": None,
            "explanation_source": None, "verified": None,
        }
        _append_audit(entry)
        _record_resolved(ctx.event_id)
        STATE.autoplay_log.append({
            "event_id": ctx.event_id, "absent": ctx.absent, "day": ctx.day + 1,
            "shift": SHIFT_NAMES.get(ctx.shift, ctx.shift).capitalize(),
            "chosen": chosen, "chosen_nurse": chosen_so.option.extra_nurse, "chosen_change_text": shift_words(describe(chosen_so.option)),
            "description": plain_change(chosen_so.option),
            "by": by, "formula_top": formula_so.option.id,
            "agrees_with_formula": chosen == formula_so.option.id, "verified": None,
            "display_text": replace_option_ids(text, option_texts),
            "plain_words": plain_words(chosen_so, ortec_so),
        })
        AUTO["done"] += 1
        _clear_event()
        return True


def _autoplay_worker(total: int, mode: str) -> None:
    try:
        for _ in range(total):
            with STATE_LOCK:
                if AUTO["cancel"]:
                    break
            if not _autoplay_step(mode):
                break
        with STATE_LOCK:  # leave the next event open so the presenter can continue by hand
            if AUTO["error"] is None and STATE.ctx is None:
                _open_next_event()
    except Exception as exc:  # never leave the UI waiting on a dead worker
        with STATE_LOCK:
            AUTO["error"] = AUTO["error"] or f"{type(exc).__name__}: {exc}"
    finally:
        with STATE_LOCK:
            AUTO["running"] = False


@app.post("/api/autoplay")
def start_autoplay(body: AutoplayIn) -> dict:
    with STATE_LOCK:
        if AUTO["running"]:
            raise HTTPException(status_code=409, detail="Autoplay running")
        _auto_reset()
        STATE.autoplay_log = []
        AUTO.update({"running": True, "total": body.events})
        threading.Thread(target=_autoplay_worker, args=(body.events, body.mode), daemon=True).start()
        return {"started": True}


@app.get("/api/autoplay/status")
def get_autoplay_status() -> dict:
    with STATE_LOCK:
        return _autoplay_status()


@app.post("/api/autoplay/stop")
def stop_autoplay() -> dict:
    with STATE_LOCK:
        if AUTO["running"]:
            AUTO["cancel"] = True
        return {"stopping": bool(AUTO["running"])}


def _read_jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


@app.post("/api/monthly-report")
def monthly_report(body: MonthlyIn) -> dict:
    """Monthly scheduler-manager review: rules compute the facts, GenAI writes the text, the text is checked."""
    with STATE_LOCK:
        seed, policy = STATE.scenario.seed, dict(STATE.policy)
    model = policy.get("model", "qwen3:8b")
    expl = _read_jsonl(RESULTS_DIR / f"e6_explanations_{model.replace(':', '-')}.jsonl")
    facts = compute_month_facts(seed, body.month, policy, audit_entries=_read_jsonl(AUDIT_PATH),
                                explanation_rows=expl)
    result = write_report(facts, model, max(60, policy.get("ui_timeout_s", 30)))
    _append_audit({"mode": "monthly_report", "month": body.month, "source": result["source"],
                   "report_status": result["check"]["status"], "error": result["error"]})
    return result


@app.get("/api/audit")
def get_audit() -> dict:
    if not AUDIT_PATH.exists():
        return {"entries": []}
    lines = AUDIT_PATH.read_text().splitlines()[-50:]
    return {"entries": [json.loads(line) for line in lines if line.strip()]}


@app.middleware("http")
async def no_cache(request, call_next):
    """Always serve fresh page files, so a browser never shows an old version after an update."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/", StaticFiles(directory=APP_DIR / "static", html=True), name="static")
