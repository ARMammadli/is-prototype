"""Ward model: nurses, shifts, demand, leave and repair availability (spec §3)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SHIFT_CODES = ("D", "E", "N")
# Hours from the start of the shift's calendar day; N ends the next morning.
SHIFT_TIMES = {"D": (7.5, 16.0), "E": (15.5, 23.0), "N": (23.0, 31.5)}
SHIFT_HOURS = {s: end - start for s, (start, end) in SHIFT_TIMES.items()}
HOURS_PER_FTE = 36.0


def shift_start(day: int, shift: str) -> float:
    return day * 24 + SHIFT_TIMES[shift][0]


def shift_end(day: int, shift: str) -> float:
    return day * 24 + SHIFT_TIMES[shift][1]


@dataclass(frozen=True)
class Nurse:
    id: str
    fte: float
    senior: bool
    night_ok: bool

    @property
    def weekly_hours(self) -> float:
        return HOURS_PER_FTE * self.fte


@dataclass
class Ward:
    nurses: list[Nurse]
    days: int
    demand: dict[str, int]
    leave: set[tuple[str, int]]
    available: set[tuple[str, int]]  # off-duty nurse-days reachable for a short-notice repair
    base_qr_pref: float = 0.0
    _index: dict[str, Nurse] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._index = {n.id: n for n in self.nurses}

    def nurse(self, nid: str) -> Nurse:
        return self._index[nid]


def load_json(name: str) -> dict:
    return json.loads((CONFIG_DIR / name).read_text())


def build_ward(cfg: dict, rng: np.random.Generator) -> Ward:
    n = cfg["n_nurses"]
    days = cfg["days"]
    ftes = rng.choice(cfg["fte_values"], size=n, p=cfg["fte_probs"])
    senior_idx = set(rng.choice(n, size=round(cfg["senior_frac"] * n), replace=False).tolist())
    exempt_idx = set(rng.choice(n, size=round(cfg["night_exempt_frac"] * n), replace=False).tolist())
    nurses = [
        Nurse(f"Nurse_{i + 1:02d}", float(ftes[i]), i in senior_idx, i not in exempt_idx)
        for i in range(n)
    ]
    leave: set[tuple[str, int]] = set()
    block = cfg["leave_block_days"]
    target = cfg["leave_frac"] * n * days
    while len(leave) < target:
        nurse = nurses[int(rng.integers(n))]
        start = int(rng.integers(0, days - block + 1))
        leave.update((nurse.id, d) for d in range(start, start + block))
    available = {
        (nu.id, d)
        for nu in nurses
        for d in range(days)
        if rng.random() < cfg["repair_availability_p"]
    }
    return Ward(nurses, days, dict(cfg["demand"]), leave, available, cfg.get("base_qr_pref", 0.0))
