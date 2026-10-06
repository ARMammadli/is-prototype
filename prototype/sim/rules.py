"""Hard scheduling rules (spec §3). Every candidate and every final roster must pass these."""
from __future__ import annotations

from sim.ward import SHIFT_HOURS, shift_end, shift_start

MIN_REST = 8.0
QR_REST = 11.0
QR_GAP = 168.0  # at most one shortened rest per rolling 7 days (Arbeidstijdenwet 5:3)
MAX_CONSEC = 6
MAX_7D_HOURS = 60.0
NIGHT_SERIES = 3
NIGHT_REST = 46.0


def nurse_violations(roster, nid: str, blocked=frozenset(), lo: int | None = None,
                     hi: int | None = None) -> list[str]:
    """Return human-readable violations for one nurse; optionally only shifts with lo <= day <= hi."""
    nurse = roster.ward.nurse(nid)
    items = roster.shifts_of(nid)
    if lo is not None:
        items = [(d, s) for d, s in items if lo <= d <= hi]
    out: list[str] = []
    for d, s in items:
        if (nid, d) in blocked:
            out.append(f"{nid} d{d}: works on a blocked day")
        if s == "N" and not nurse.night_ok:
            out.append(f"{nid} d{d}: night-exempt nurse on a night shift")
    qr_times: list[float] = []
    for (d1, s1), (d2, s2) in zip(items, items[1:]):
        rest = shift_start(d2, s2) - shift_end(d1, s1)
        if rest < MIN_REST:
            out.append(f"{nid} d{d2}: rest {rest:.1f}h below 8h")
        elif rest < QR_REST:
            qr_times.append(shift_start(d2, s2))
    for t1, t2 in zip(qr_times, qr_times[1:]):
        if t2 - t1 < QR_GAP:
            out.append(f"{nid}: two quick returns within 7 days")
    hours = {d: SHIFT_HOURS[s] for d, s in items}
    for d in hours:
        if sum(h for dd, h in hours.items() if d <= dd < d + 7) > MAX_7D_HOURS:
            out.append(f"{nid} d{d}: more than 60h in 7 days")
    run, prev = 0, None
    for d, _ in items:
        run = run + 1 if prev is not None and d == prev + 1 else 1
        prev = d
        if run > MAX_CONSEC:
            out.append(f"{nid} d{d}: more than 6 consecutive days")
    i = 0
    while i < len(items):
        if items[i][1] != "N":
            i += 1
            continue
        j = i
        while j + 1 < len(items) and items[j + 1][1] == "N" and items[j + 1][0] == items[j][0] + 1:
            j += 1
        if j - i + 1 >= NIGHT_SERIES and j + 1 < len(items):
            rest = shift_start(*items[j + 1]) - shift_end(*items[j])
            if rest < NIGHT_REST:
                out.append(f"{nid} d{items[j + 1][0]}: rest {rest:.1f}h after night series below 46h")
        i = j + 1
    return out


def roster_violations(roster, blocked=frozenset()) -> list[str]:
    return [v for n in roster.ward.nurses for v in nurse_violations(roster, n.id, blocked)]
