"""Acceptance models for the agentic-future test (spec §6, E4). Probabilities are assumptions."""
from __future__ import annotations

P_ACCEPT = 0.9
P_PICKY_LOW = 0.3


def accepts(mode: str, rng, nurse_detail: dict, median_strain: float) -> bool:
    if mode == "today":
        return True
    if mode == "permissive":
        return bool(rng.random() < P_ACCEPT)
    if mode == "picky":
        adds_qr = nurse_detail["after"]["QR"] > nurse_detail["before"]["QR"]
        calm = not adds_qr and nurse_detail["strain_before"] <= median_strain
        return bool(rng.random() < (P_ACCEPT if calm else P_PICKY_LOW))
    raise ValueError(f"unknown acceptance mode {mode!r}")
