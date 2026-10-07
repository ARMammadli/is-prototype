"""Pre-generate GenAI answers for a server that cannot run the model (LLM_MODE=replay there).

Drives the real endpoints the way the UI does, with LLM_MODE=record, so every prompt the public demo can
send on the main paths is stored in config/llm_replay.jsonl (exact-prompt keys; see llm/ollama_client.py):
  1. Demo: open, explain, translate the example sentence, approve, explain again, then the rest of ward 1
     under the approved policy (accepting the rule's choice) and its monthly reports.
  2. Each ward (Setup: wards 1-5, start weeks 1-7): explain each sick call and accept the rule's choice.
     Week 1 runs to the end; later start weeks record the first --per-start sick calls.
  3. Monthly reports (months 1-2) for each ward under the default policy.
Needs `ollama serve` with qwen3:8b. Resumable: stored prompts are not asked again.

  LLM_MODE=record python3 -m evaluation.pregenerate [--per-start 10] [--wards 0 1 2 3 4]
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

if os.environ.get("LLM_MODE") != "record":
    sys.exit("Run with LLM_MODE=record (and ollama serve running).")
os.environ.setdefault("ROSTER_AUDIT_PATH", str(Path(tempfile.mkdtemp()) / "audit.jsonl"))  # keep the live log clean

from fastapi.testclient import TestClient  # noqa: E402

from app.server import DEMO_POLICY_TEXT, app  # noqa: E402
from llm.ollama_client import REPLAY_PATH, is_available  # noqa: E402

EXTRA_SENTENCES = (
    "Night shifts wear people out the most. Weigh them twice as much.",
    "Avoid quick returns above everything else.",
)
counts = {"explain": 0, "explain_failed": 0, "translate": 0, "monthly": 0, "events": 0}


def post(c: TestClient, path: str, body: dict | None = None) -> dict:
    r = c.post(path, json=body)
    r.raise_for_status()
    return r.json()


def explain(c: TestClient) -> None:
    r = post(c, "/api/explain")
    counts["explain"] += 1
    if not r.get("framing"):
        counts["explain_failed"] += 1
        print(f"  explain failed: {r.get('error')}", flush=True)


def walk(c: TestClient, state: dict, limit: int | None, label: str) -> None:
    """From an opened ward: per sick call, explain (as the UI does on load) and accept the rule's choice."""
    n, t0 = 0, time.time()
    while limit is None or n < limit:
        if not state.get("event"):
            r = post(c, "/api/next-event")
            if r["done"]:
                break
            state = r["state"]
            continue
        ev = state["event"]
        if not ev.get("unfilled"):
            explain(c)
            top = c.get("/api/options", params={"mode": "strain"}).json()["options"][0]
            state = post(c, "/api/apply", {"event_id": ev["event_id"], "option_id": top["id"], "mode": "strain"})["state"]
            n += 1
            counts["events"] += 1
        else:
            state = {**state, "event": None}
    print(f"{label}: {n} sick calls, {time.time() - t0:.0f} s", flush=True)


def open_ward(c: TestClient, seed: int, week: int) -> dict:
    """Same calls as the UI's Start (startPresenterInner)."""
    state = post(c, "/api/scenario", {"seed": seed})
    if week > 1:
        state = post(c, "/api/fast-forward", {"to_day": (week - 1) * 7 + 1, "mode": "baseline", "reset_history": True})["state"]
    return state


def monthly(c: TestClient, label: str) -> None:
    for month in (1, 2):
        r = post(c, "/api/monthly-report", {"month": month})
        counts["monthly"] += 1
        print(f"{label} month {month}: {'ok' if r.get('report') else r.get('error')}", flush=True)


def translate(c: TestClient, text: str) -> dict | None:
    r = post(c, "/api/policy/translate", {"text": text})
    counts["translate"] += 1
    print(f"translate {text[:40]!r}: {'ok' if r.get('proposal') else r.get('error')}", flush=True)
    return r.get("proposal")


def demo(c: TestClient) -> None:
    state = post(c, "/api/demo")
    explain(c)
    for text in EXTRA_SENTENCES:
        translate(c, text)
    proposal = translate(c, DEMO_POLICY_TEXT)
    if not proposal:
        print("demo translate failed; skipping the approved-policy path", flush=True)
        return
    p = c.get("/api/policy").json()
    r = c.put("/api/policy", json={"weights": proposal["weights"], "forward_days": p["forward_days"],
                                   "squared": p["squared"], "source": "genai", "policy_text": DEMO_POLICY_TEXT})
    r.raise_for_status()
    walk(c, c.get("/api/state").json(), None, "demo, approved policy")
    monthly(c, "demo ward 1 (approved policy)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-start", type=int, default=10, help="sick calls recorded for start weeks 2-7")
    ap.add_argument("--wards", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    args = ap.parse_args()
    if not is_available():
        sys.exit("Ollama is not reachable; start `ollama serve` (qwen3:8b).")
    t0 = time.time()
    with TestClient(app) as c:
        demo(c)
        for seed in args.wards:
            post(c, "/api/demo")  # back to the default policy
            walk(c, open_ward(c, seed, 1), None, f"ward {seed + 1} week 1")
            monthly(c, f"ward {seed + 1}")
            for week in range(2, 8):
                walk(c, open_ward(c, seed, week), args.per_start, f"ward {seed + 1} week {week}")
    print(f"done in {time.time() - t0:.0f} s: {counts}; store {REPLAY_PATH}", flush=True)


if __name__ == "__main__":
    main()
