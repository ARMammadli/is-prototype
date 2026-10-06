"""E5 — AI decides: a local LLM picks the repair option; fallback to the strain formula (resumable)."""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx
import pandas as pd

from evaluation import stats as _stats
from evaluation.stats import paired_table
from llm.decide import build_decision_payload, decide
from llm.ollama_client import OLLAMA_URL, is_available
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.policies import rank_options
from sim.ward import load_json

E5_METRICS = ["QR_total", "gini_strain", "max_qr", "nurses_qr_ge3_28d", "top10_qr_share", "unfilled",
              "changes_per_repair", "SN_total", "n_events"]
AI_EXTRA = ["agreement_rate", "fallback_rate", "verified_rate", "latency_p50_ms"]

def _results_dir():
    return _stats.RESULTS_DIR  # looked up at call time so tests can monkeypatch it

class FallbackAbort(RuntimeError):
    """Raised when a seed's fallback rate is so high the run is not a valid AI result."""

MAX_FALLBACK_RATE = 0.5

def model_available(model: str, timeout: float = 5.0) -> bool:
    try:
        names = {m.get("name") for m in httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout).json().get("models", [])}
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, AttributeError):
        return False
    return model in names or (":" not in model and f"{model}:latest" in names)

def make_chooser(policy: dict, model: str, timeout: float, seed: int | None = None,
                 lines: list | None = None, counters: dict | None = None):
    """Build a chooser(ctx, scored) -> (option_id | None, info).

    Decision log lines are buffered in `lines` (written with the seed's CSV row by persist_seed).
    `counters['skipped']` counts <2-option events."""
    lines = lines if lines is not None else []
    counters = counters if counters is not None else {}
    counters.setdefault("skipped", 0)

    def chooser(ctx, scored):
        if len(scored) < 2:
            counters["skipped"] += 1
            return None, {"fallback": False, "skipped": True}
        payload = build_decision_payload(ctx, scored, policy)
        formula_top = rank_options(scored, "strain")[0].option.id
        r = decide(payload, formula_top, model, timeout)
        dec = r["decision"]
        chosen = dec["chosen_option"] if dec is not None else None
        info = {"agrees": bool(r["agrees"]), "fallback": dec is None, "latency_ms": r["latency_ms"],
                "verified": bool(r["check"]["verified"]), "skipped": False}
        lines.append(json.dumps({
                "seed": chooser.seed, "event_id": ctx.event_id, "chosen": chosen,
                "formula_top": formula_top, "agrees": info["agrees"], "fallback": info["fallback"],
                "verified": info["verified"], "latency_ms": info["latency_ms"],
                "main_tradeoff": dec.get("main_tradeoff") if dec else None,
                "n_candidates": len(payload["options"])}))
        return chosen, info

    chooser.seed = seed
    chooser.lines = lines
    return chooser

def ai_rates(records) -> dict:
    ai = [r for r in records if r.ai_agrees is not None]
    n = len(ai)
    lat = [r.ai_latency_ms for r in ai if r.ai_latency_ms is not None]
    return {
        "agreement_rate": sum(bool(r.ai_agrees) for r in ai) / n if n else float("nan"),
        "fallback_rate": sum(r.ai_fallback for r in ai) / n if n else float("nan"),
        "verified_rate": sum(bool(r.ai_verified) for r in ai) / n if n else float("nan"),
        "latency_p50_ms": float(pd.Series(lat).median()) if lat else float("nan"),
        "n_ai_decisions": n,
        "n_skipped": sum(1 for r in records if r.ai_agrees is None),
    }

def _wmean(df: pd.DataFrame, col: str) -> float:
    w = df["n_ai_decisions"].astype(float)
    return float((df[col] * w).sum() / w.sum()) if w.sum() > 0 else float("nan")

def build_e5_outputs(rd=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (summary, stats) from e5_runs.csv + the matching e1 baseline/strain rows."""
    rd = rd or _results_dir()
    if not (rd / "e1_runs.csv").exists():
        raise FileNotFoundError(f"{rd / 'e1_runs.csv'} is missing; run the E1 evaluation first.")
    ai = pd.read_csv(rd / "e5_runs.csv")
    e1 = pd.read_csv(rd / "e1_runs.csv")
    e1 = e1[e1.policy.isin(["baseline", "strain"])]
    common = set(ai.seed) & set(e1[e1.policy == "baseline"].seed) & set(e1[e1.policy == "strain"].seed)
    ai = ai[ai.seed.isin(common)]
    e1 = e1[e1.seed.isin(common)]
    allruns = pd.concat([e1, ai], ignore_index=True)
    summary = allruns.groupby("policy")[E5_METRICS].mean().reindex(["baseline", "strain", "ai"]).dropna(how="all")
    for c in ("agreement_rate", "fallback_rate", "verified_rate"):
        summary.loc["ai", c] = _wmean(ai, c)  # pooled by n_ai_decisions
    summary.loc["ai", "latency_p50_ms"] = float(ai["latency_p50_ms"].median())  # median of per-seed medians
    summary = summary.reset_index()
    stats = pd.concat([paired_table(allruns, E5_METRICS, a=a, b="ai").assign(comparison=f"ai vs {a}")
                       for a in ("strain", "baseline")], ignore_index=True)
    return summary, stats

def write_outputs() -> pd.DataFrame:
    rd = _results_dir()
    summary, stats = build_e5_outputs(rd)
    summary.to_csv(rd / "e5_summary.csv", index=False)
    stats.to_csv(rd / "e5_stats.csv", index=False)
    return summary

def run_seed(seed: int, policy: dict, model: str, timeout: float):
    """Run one AI seed. Returns (row, decision_lines, skipped). Raises FallbackAbort if mostly fallbacks."""
    counters: dict = {}
    chooser = make_chooser(policy, model, timeout, seed=seed, counters=counters)
    res = run_scenario(seed, "ai", policy, chooser=chooser)
    row = run_metrics(res, policy["weights"])
    row.update(seed=seed, policy="ai", model=model, **ai_rates(res.records))
    if row["n_ai_decisions"] and row["fallback_rate"] > MAX_FALLBACK_RATE:
        raise FallbackAbort(f"seed {seed}: fallback_rate={row['fallback_rate']:.2f} > {MAX_FALLBACK_RATE}")
    return row, chooser.lines, counters["skipped"]

def persist_seed(rd, row: dict, lines: list) -> None:
    """Write the seed's decision lines, then its CSV row (the row marks the seed as done)."""
    with open(rd / "e5_decisions.jsonl", "a") as fh:
        fh.writelines(line + "\n" for line in lines)
    runs_path = rd / "e5_runs.csv"
    pd.DataFrame([row]).to_csv(runs_path, mode="a", header=not runs_path.exists(), index=False)

def prune_decisions(rd, done: set) -> None:
    """Drop JSONL lines of seeds that have no CSV row (a crash between decisions and the row)."""
    path = rd / "e5_decisions.jsonl"
    if not path.exists():
        return
    keep = [ln for ln in path.read_text().splitlines()
            if ln.strip() and json.loads(ln).get("seed") in done]
    path.write_text("".join(ln + "\n" for ln in keep))

def main() -> None:
    policy = load_json("policy.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--model", default=policy["model"])
    ap.add_argument("--timeout", type=float, default=60)
    args = ap.parse_args()
    if not is_available():
        print(f"Ollama is not reachable at {OLLAMA_URL}. Start it with `ollama serve` and run "
              f"`ollama pull {args.model}` first.")
        sys.exit(2)
    if not model_available(args.model):
        print(f"Model {args.model!r} is not listed by Ollama at {OLLAMA_URL}/api/tags. "
              f"Run `ollama pull {args.model}` first.")
        sys.exit(2)
    rd = _results_dir()
    rd.mkdir(exist_ok=True)
    runs_path = rd / "e5_runs.csv"
    done = {int(x) for x in pd.read_csv(runs_path).seed} if runs_path.exists() else set()
    prune_decisions(rd, done)
    t0 = time.perf_counter()
    for seed in range(args.seeds):
        if seed in done:
            print(f"seed {seed}: already done, skipping", flush=True)
            continue
        try:
            row, lines, skipped = run_seed(seed, policy, args.model, args.timeout)
        except FallbackAbort as exc:
            print(f"!!! WARNING: {exc}. The model is not answering usefully (timeout, model not loaded?). "
                  f"Row NOT saved; fix Ollama and re-run to resume from this seed.", flush=True)
            sys.exit(2)
        persist_seed(rd, row, lines)
        print(f"seed {seed}: agree={row['agreement_rate']:.2f} fallback={row['fallback_rate']:.2f} "
              f"verified={row['verified_rate']:.2f} p50={row['latency_p50_ms']:.0f}ms "
              f"decisions={row['n_ai_decisions']} skipped={skipped} "
              f"elapsed={time.perf_counter() - t0:.0f}s", flush=True)
        try:
            write_outputs()
        except FileNotFoundError as exc:
            print(f"warning: {exc}", flush=True)
    print(write_outputs().to_string(index=False), flush=True)

if __name__ == "__main__":
    main()
