"""Deterministic per-decision comparison of two scored options (no LLM)."""
from __future__ import annotations

from sim.policies import apply_changes, describe, revert_changes
from sim.ward import shift_end, shift_start


_SHIFT_NAME = {"D": "day", "E": "evening", "N": "night"}


def nurse_name(nid) -> str:
    """Display name for a nurse id: 'Nurse_08' -> 'Nurse 08' (display only)."""
    return str(nid).replace("_", " ")


def plain_change(option) -> str:
    """One plain sentence for a repair option (no ids, no codes); used for display and GenAI text."""
    ch = option.changes
    sh = lambda c: _SHIFT_NAME.get(c, str(c))  # noqa: E731
    filler = next((c for c in ch if c.old is None and c.new is not None), None)
    mover = next((c for c in ch if c.old is not None and c.new is not None), None)
    if mover is None:
        c = filler or ch[0]
        return f"Call in {nurse_name(c.nurse)} for the {sh(c.new)} shift"
    text = f"Move {nurse_name(mover.nurse)} from the {sh(mover.old)} shift to the {sh(mover.new)} shift"
    if filler is not None:
        text += f"; call in {nurse_name(filler.nurse)} for the {sh(filler.new)} shift"
    return text


def _g(x) -> str:
    return f"{x:g}"


def _delta(n: dict) -> float:
    return n["strain_after"] - n["strain_before"]


def _qr_change(n: dict) -> int:
    return n["after"]["QR"] - n["before"]["QR"]


def _load_move(n: dict | None) -> dict | None:
    return None if n is None else {"nurse": n["nurse"], "before": n["strain_before"], "after": n["strain_after"],
                                   "counts": dict(n["before"])}


def pick_summary(so) -> dict:
    nurses = so.nurses
    up = [n for n in nurses if _delta(n) > 0]
    down = [n for n in nurses if _delta(n) < 0]
    return {
        "id": so.option.id,
        "change_text": describe(so.option),
        "description": plain_change(so.option),
        "new_quick_returns": sum(_qr_change(n) for n in nurses),
        "heaviest_before": max(n["strain_before"] for n in nurses),
        "heaviest_after": max(n["strain_after"] for n in nurses),
        "people_disturbed": len({n["nurse"] for n in nurses}),
        "involved": [{"nurse": n["nurse"], "before": n["strain_before"], "after": n["strain_after"],
                      "qr_change": _qr_change(n), "counts": dict(n["before"])} for n in nurses],
        "load_added": so.delta_strain,
        "extra_work": _load_move(max(up, key=_delta) if up else None),
        "relief": _load_move(min(down, key=_delta) if down else None),
    }


def _biggest(nurses: list[dict]) -> dict:
    return max(nurses, key=lambda n: abs(_delta(n)))


def _riser(nurses: list[dict]) -> dict | None:
    up = [n for n in nurses if _delta(n) > 0]
    return max(up, key=_delta) if up else None


def _loads(n: dict) -> str:
    return f"load {_g(n['strain_before'])} → {_g(n['strain_after'])}"


def _people(k: int) -> str:
    return f"{k} person" if k == 1 else f"{k} people"


def plain_words(ours_so, ortec_so) -> str:
    o_id, r_id = ours_so.option.id, ortec_so.option.id
    if o_id == r_id:
        return f"Both rules agree: {o_id} ({describe(ours_so.option)})."
    ours = ours_so.nurses
    relieved = [n for n in ours if _qr_change(n) < 0]
    if relieved:
        n = _biggest(relieved)
        text = f"{o_id} moves {n['nurse']} (load {_g(n['strain_before'])}) off a quick return"
    else:
        extra = getattr(ours_so.option, "extra_nurse", None)
        n = next((m for m in ours if m["nurse"] == extra), None) or _riser(ours) or _biggest(ours)
        text = f"{o_id} gives the shift to {n['nurse']}"
        if _delta(n) > 0:
            text += f" ({_loads(n)})"
    created = [m for m in ours if _qr_change(m) > 0]
    if created:
        text += f", but it creates a new quick return for {_biggest(created)['nurse']}"
    theirs = ortec_so.nurses
    new_qr = [m for m in theirs if _qr_change(m) > 0]
    if new_qr:
        m = max(new_qr, key=_delta)
        part = f"give {m['nurse']} a new quick return ({_loads(m)})"
    elif (m := _riser(theirs)) is not None:
        part = f"add load to {m['nurse']} ({_loads(m)})"
    else:
        part = "not add load to anyone"
    return (f"{text}. ORTEC's pick ({r_id}) would {part}. "
            f"Trade-off: ours disturbs {_people(len(ours))} vs {len(theirs)}.")


def ward_context(strains) -> dict:
    """Ward tiredness at the event: 75th ('tired_at') and 50th ('median_at') percentile of per-nurse strain."""
    vals = sorted(float(v) for v in (strains.values() if hasattr(strains, "values") else strains))
    if not vals:
        return {"tired_at": None, "median_at": None}

    def pct(q: float) -> float:
        pos = q * (len(vals) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(vals) - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)
    return {"tired_at": pct(0.75), "median_at": pct(0.5)}

def is_tired(strain_before: float, ward: dict | None) -> bool:
    """Tired = at or above the ward's 75th percentile (and above zero)."""
    t = (ward or {}).get("tired_at")
    return t is not None and t > 0 and strain_before >= t

WINDOW_WORDS = "in the past and next 28 days"
_COUNT_WORD = (("QR", "quick return", "quick returns"), ("N", "night", "nights"), ("LR", "long run", "long runs"),
               ("OT", "overtime hour", "overtime hours"), ("SN", "short-notice change", "short-notice changes"))


def counts_text(counts: dict | None) -> str:
    """'3 quick returns, 4 nights' from a nurse's counts over the past and next 28 days (non-zero items only)."""
    if not counts:
        return ""
    parts = [f"{_g(counts[k])} {one if counts[k] == 1 else many}" for k, one, many in _COUNT_WORD if counts.get(k)]
    return ", ".join(parts) if parts else "no quick returns, nights, long runs, overtime or short-notice changes"


def tiredness_word(strain_before: float, ward: dict | None) -> str:
    """'high' at/above the ward's 75th percentile, 'medium' at/above the median, else 'low'."""
    if is_tired(strain_before, ward):
        return "high"
    m = (ward or {}).get("median_at")
    return "medium" if m is not None and m > 0 and strain_before >= m else "low"

def _who(nurse, before, ward: dict | None, counts: dict | None = None) -> str:
    """'Nurse 67 (recent load: high, 3 quick returns, 4 nights in the past and next 28 days)'."""
    c = counts_text(counts)
    return f"{nurse_name(nurse)} (recent load: {tiredness_word(before, ward)}" + (f", {c} {WINDOW_WORDS})" if c else ")")

def who_words(ours: dict, ortec: dict, ward: dict | None = None) -> str | None:
    """One plain sentence from two pick summaries (no ids, no LLM); None when there is nothing to say."""
    if ours["id"] == ortec["id"]:
        return "Today's software and the hospital rule would make the same fix."
    relief, extra = ours.get("relief"), ours.get("extra_work")
    if ours["new_quick_returns"] < 0 and relief:
        left = f"{_who(relief['nurse'], relief['before'], ward, relief.get('counts'))} is moved off a short rest"
    elif extra:
        left = f"{_who(extra['nurse'], extra['before'], ward, extra.get('counts'))} takes the extra shift"
    else:
        return None
    r_extra = ortec.get("extra_work")
    if ortec["new_quick_returns"] > 0 and r_extra:
        right = f"would make {_who(r_extra['nurse'], r_extra['before'], ward, r_extra.get('counts'))} come back after a short rest"
    elif r_extra:
        right = f"would add work to {_who(r_extra['nurse'], r_extra['before'], ward, r_extra.get('counts'))}"
    else:
        right = "would not add load to anyone"
    return f"With the hospital rule, {left}; today's software {right}."

def _nurses_of(pick: dict) -> list[dict]:
    return pick.get("involved") or []

def _short_rest_nurse(pick: dict, sign: int) -> dict | None:
    """The involved nurse with the biggest quick-return change in this direction (sign +1 new, -1 removed)."""
    hits = [n for n in _nurses_of(pick) if n["qr_change"] * sign > 0]
    return max(hits, key=lambda n: (abs(n["qr_change"]), n["before"])) if hits else None

def _result(pick: dict, ward: dict | None) -> str:
    """Deterministic 'Result: ...' line (recent load as a word plus the counts behind it)."""
    nm = lambda n: _who(n["nurse"], n["before"], ward, n.get("counts"))  # noqa: E731
    made = _short_rest_nurse(pick, +1)
    freed = _short_rest_nurse(pick, -1)
    if freed is not None and made is None:
        return f"Result: {nm(freed)} is moved off a short rest."
    if made is not None:
        return f"Result: {nm(made)} gets a short rest."
    relief = pick.get("relief")
    if relief:
        return f"Result: {nm(relief)} gets relief."
    return "Result: no one gets relief."

REST_OK_H = 11.0
REST_RADIUS = 2


def _hours(x: float) -> str:
    return f"{round(x, 1):g} h"


def _min_rest(roster, nid: str, lo: int, hi: int) -> float | None:
    """Shortest rest between consecutive shifts of one nurse, shifts on days lo..hi only (None: no pair)."""
    items = [(d, s) for d, s in roster.shifts_of(nid) if lo <= d <= hi]
    gaps = [shift_start(d2, s2) - shift_end(d1, s1) for (d1, s1), (d2, s2) in zip(items, items[1:])]
    return min(gaps) if gaps else None


def rest_effect(roster, changes, radius: int = REST_RADIUS) -> list[dict]:
    """Per affected nurse: minimum rest within +-radius days of the change days, before vs after the changes.

    The roster is changed temporarily and always restored. Entries: {nurse, before, after} (hours, None = no pair).
    """
    days: dict[str, list[int]] = {}
    for c in changes:
        days.setdefault(c.nurse, []).append(c.day)
    span = {n: (min(d) - radius, max(d) + radius) for n, d in days.items()}
    before = {n: _min_rest(roster, n, *span[n]) for n in span}
    apply_changes(roster, changes)
    try:
        after = {n: _min_rest(roster, n, *span[n]) for n in span}
    finally:
        revert_changes(roster, changes)
    return [{"nurse": n, "before": before[n], "after": after[n]} for n in span]


def rest_lines(roster, option) -> list[str]:
    """Plain rest-hour lines for one option (no LLM): warnings first, then improvements, else 'everyone keeps 11 h+'."""
    bad, good = [], []
    all_ok = True
    for e in rest_effect(roster, option.changes):
        b, a, who = e["before"], e["after"], nurse_name(e["nurse"])
        b_ok = b is None or b >= REST_OK_H
        a_ok = a is None or a >= REST_OK_H
        all_ok = all_ok and a_ok
        if not a_ok and b_ok:
            bad.append(f"{who} comes back after only {_hours(a)} rest ⚠️")
        elif not a_ok and a < b - 1e-9:
            bad.append(f"{who}: rest drops from {_hours(b)} to {_hours(a)} ⚠️")
        elif not b_ok and a_ok:
            good.append(f"{who}: rest goes from {_hours(b)} to {'11 h+' if a is None else _hours(a)} ✓")
        elif not b_ok and a > b + 1e-9:
            good.append(f"{who}: rest goes from {_hours(b)} to {_hours(a)}")
    lines = bad + good
    if all_ok and not good:
        lines = ["everyone keeps 11 h+ rest ✓"]
    return lines


def card_lines(ours: dict, ortec: dict, ward: dict | None = None, rest: dict | None = None) -> dict:
    """Plain, deterministic card text for the presenter (no LLM).

    'ours'/'ortec': action, result, cost lines. 'rest_lines': {'ours': [...], 'ortec': [...]} shown after the action.
    """
    o_lines = [ours["description"], _result(ours, ward)]
    if ours["people_disturbed"] > ortec["people_disturbed"]:
        o_lines.append(f"Cost: changes {ours['people_disturbed']} people's shifts instead of {ortec['people_disturbed']}.")
    r_lines = [ortec["description"], _result(ortec, ward),
               f"Changes {_people(ortec['people_disturbed'])}'s shift." if ortec["people_disturbed"] == 1
               else f"Changes {ortec['people_disturbed']} people's shifts."]
    rest = rest or {}
    return {"ours": o_lines, "ortec": r_lines,
            "rest_lines": {"ours": list(rest.get("ours", [])), "ortec": list(rest.get("ortec", []))}}


def _is_short(h) -> bool:
    return h is not None and h < REST_OK_H


def difference_text(ours: dict, ortec: dict, rest_fx: dict | None = None, ward: dict | None = None) -> str | None:
    """One or two plain sentences on what the hospital rule's pick does differently from today's software.

    Written by code from the roster data, never by GenAI.

    'ours'/'ortec' are pick_summary dicts; 'rest_fx' is {'ours': rest_effect(...), 'ortec': rest_effect(...)}.
    Returns None when there is nothing concrete to say.
    """
    if ours["id"] == ortec["id"]:
        return "Both chose the same fix here."
    rest_fx = rest_fx or {}
    inv = (ortec.get("involved") or []) + (ours.get("involved") or [])
    load = {n["nurse"]: n["before"] for n in inv}
    counts = {n["nurse"]: n.get("counts") for n in inv}
    who = lambda nid: _who(nid, load.get(nid, 0.0), ward, counts.get(nid))  # noqa: E731
    ortec_nurses = {n["nurse"] for n in ortec.get("involved") or []}
    ours_short = {e["nurse"] for e in rest_fx.get("ours", []) if _is_short(e["after"])}
    parts = []
    # Each branch names the worst case: the shortest rest before (fixed) or after (made / own).
    fixed = [e for e in rest_fx.get("ours", []) if _is_short(e["before"]) and e["nurse"] not in ortec_nurses
             and (e["after"] is None or e["after"] > e["before"])]
    if fixed:
        e = min(fixed, key=lambda x: x["before"])
        after = "11 h+" if e["after"] is None else _hours(e["after"])
        parts.append(f"Today's software leaves {who(e['nurse'])} with only {_hours(e['before'])} rest between two shifts; "
                     f"the hospital rule changes the plan so they get {after}.")
    made = [e for e in rest_fx.get("ortec", []) if _is_short(e["after"]) and not _is_short(e["before"])
            and e["nurse"] not in ours_short]
    if made:
        e = min(made, key=lambda x: x["after"])
        parts.append(f"Today's software would bring {who(e['nurse'])} back after only {_hours(e['after'])} rest; the hospital rule avoids that.")
    own = [e for e in rest_fx.get("ours", []) if _is_short(e["after"]) and not _is_short(e["before"])]
    if own:
        e = min(own, key=lambda x: x["after"])
        parts.append(f"Note: the hospital rule's fix brings {who(e['nurse'])} back after only {_hours(e['after'])} rest.")
    if not parts:
        rx, ox = ortec.get("extra_work"), ours.get("extra_work")
        if rx and ox and rx["nurse"] != ox["nurse"]:
            parts.append(f"Today's software gives the extra work to {who(rx['nurse'])}; the hospital rule gives it to {who(ox['nurse'])}.")
    return " ".join(parts) or None
