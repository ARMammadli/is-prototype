"""Template explanation used when the LLM is unavailable (spec §5). Uses only payload numbers."""
from __future__ import annotations

from llm.checker import comparison_pair, ground_truth_tradeoff
from sim.strain import METRICS


def _desc(opt: dict) -> str:
    return "; ".join(f"{c['nurse']}: {c['from'] or 'off'} → {c['to'] or 'off'}" for c in opt["changes"])


def _changed(opt: dict) -> list[dict]:
    return [{"nurse": nd["nurse"], "metric": m, "before": nd["before"][m], "after": nd["after"][m]}
            for nd in opt["nurses"] for m in METRICS if nd["after"][m] != nd["before"][m]]


def _fmt(claims: list[dict]) -> str:
    return ", ".join(f"{c['nurse']} {c['metric']} {c['before']}→{c['after']}" for c in claims[:3])


def template_explanation(payload: dict) -> dict:
    top, other = comparison_pair(payload)
    tradeoff = ground_truth_tradeoff(payload)
    top_claims = _changed(top)
    text = f"Recommended {top['id']} ({_desc(top)})."
    claims = list(top_claims)
    if other is None:
        text += " It is the only feasible option."
    else:
        other_claims = _changed(other)
        claims += other_claims
        text += f" Compared with {other['id']} ({_desc(other)}), the main difference is " \
                f"{tradeoff.replace('_', ' ')}."
        if other_claims:
            text += f" {other['id']}: {_fmt(other_claims)}."
        if top_claims:
            text += f" {top['id']}: {_fmt(top_claims)}."
    return {"recommended_option": top["id"], "main_tradeoff": tradeoff, "claims": claims, "text": text}
