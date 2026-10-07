from types import SimpleNamespace as NS

from helpers import make_ward, roster_with
from sim.compare import (card_lines, is_tired, nurse_name, pick_summary, plain_change, plain_words,
                         rest_effect, rest_lines, tiredness_word, ward_context, who_words)
from sim.policies import Change, Option
from sim.metrics import plan_scoreboard

W = {"QR": 3.0, "N": 1.0, "LR": 2.0, "OT": 0.5, "SN": 1.5}


def _nd(nurse, qb, qa, sb, sa):
    return {"nurse": nurse, "before": {"QR": qb}, "after": {"QR": qa},
            "strain_before": sb, "strain_after": sa}


def _so(oid, nurses, delta):
    ch = [NS(nurse=n["nurse"], old=None, new="D") for n in nurses]
    return NS(option=NS(id=oid, changes=ch), nurses=nurses, delta_strain=delta)


def test_pick_summary():
    so = _so("Option_2", [_nd("Nurse_01", 0, 1, 2.0, 5.0), _nd("Nurse_02", 1, 0, 4.0, 1.0)], 0.0)
    s = pick_summary(so)
    assert s == {"id": "Option_2", "change_text": "Nurse_01: off → D; Nurse_02: off → D",
                 "description": "Call in Nurse 01 for the day shift",
                 "involved": [{"nurse": "Nurse_01", "before": 2.0, "after": 5.0, "qr_change": 1, "counts": {"QR": 0}},
                              {"nurse": "Nurse_02", "before": 4.0, "after": 1.0, "qr_change": -1, "counts": {"QR": 1}}],
                 "new_quick_returns": 0, "heaviest_before": 4.0, "heaviest_after": 5.0,
                 "people_disturbed": 2, "load_added": 0.0,
                 "extra_work": {"nurse": "Nurse_01", "before": 2.0, "after": 5.0, "counts": {"QR": 0}},
                 "relief": {"nurse": "Nurse_02", "before": 4.0, "after": 1.0, "counts": {"QR": 1}}}
    neg = pick_summary(_so("Option_3", [_nd("Nurse_02", 2, 0, 6.0, 1.0)], -5.0))
    assert neg["new_quick_returns"] == -2
    assert neg["extra_work"] is None and neg["relief"]["nurse"] == "Nurse_02"


def test_plain_words_agree_and_differ():
    a = _so("Option_1", [_nd("Nurse_02", 0, 0, 1.0, 2.0)], 1.0)
    assert plain_words(a, a) == "Both rules agree: Option_1 (Nurse_02: off → D)."
    b = _so("Option_2", [_nd("Nurse_01", 0, 1, 1.0, 4.5)], 3.5)
    t = plain_words(a, b)
    assert t == ("Option_1 gives the shift to Nurse_02 (load 1 → 2). ORTEC's pick (Option_2) would give "
                 "Nurse_01 a new quick return (load 1 → 4.5). Trade-off: ours disturbs 1 person vs 1.")
    relief = _so("Option_3", [_nd("Nurse_03", 1, 0, 6.0, 5.0)], -1.0)
    plain = _so("Option_4", [_nd("Nurse_04", 0, 0, 2.0, 3.0)], 1.0)
    t2 = plain_words(relief, plain)
    assert t2.startswith("Option_3 moves Nurse_03 (load 6) off a quick return.")
    assert "ORTEC's pick (Option_4) would add load to Nurse_04 (load 2 → 3)." in t2


def test_plan_scoreboard():
    w = make_ward(n=2, days=14)
    r = roster_with(w, {"Nurse_01": {1: "E", 2: "D"}, "Nurse_02": {3: "N"}})
    r.added.add(("Nurse_01", 2))
    sb = plan_scoreboard(r, w, W)
    assert sb["quick_returns"] == 1 and sb["nurses_qr_ge3_28d"] == 0
    assert sb["shifts_changed"] == 1 and sb["short_notice_calls"] == 0
    assert sb["max_load"] == round(max(sb["max_load"], 0), 1) and sb["max_load"] >= 3.0


def test_plain_words_unchanged_and_decreased_load():
    ours = _so("Option_1", [_nd("Nurse_02", 0, 0, 4.0, 4.0)], 0.0)
    flat = _so("Option_2", [_nd("Nurse_03", 0, 0, 4.0, 4.0)], 0.0)
    t = plain_words(ours, flat)
    assert t.startswith("Option_1 gives the shift to Nurse_02.")
    assert "would not add load to anyone" in t and "→" not in t
    down = _so("Option_3", [_nd("Nurse_04", 0, 0, 5.0, 3.0), _nd("Nurse_05", 0, 0, 1.0, 2.0)], -1.0)
    t = plain_words(ours, down)
    assert "add load to Nurse_05 (load 1 → 2)" in t and "Nurse_04" not in t
    t = plain_words(down, ours)
    assert "gives the shift to Nurse_05 (load 1 → 2)" in t


def test_plain_change_variants():
    direct = Option("Option_1", "direct", (Change("Nurse_08", 3, None, "E"),))
    assert plain_change(direct) == "Call in Nurse 08 for the evening shift"
    backfill = Option("Option_2", "move", (Change("Nurse_59", 3, "N", "E"), Change("Nurse_53", 3, None, "N")))
    assert plain_change(backfill) == ("Move Nurse 59 from the night shift to the evening shift; "
                                      "call in Nurse 53 for the night shift")
    plain_move = Option("Option_3", "move", (Change("Nurse_59", 3, "N", "E"),))
    assert plain_change(plain_move) == "Move Nurse 59 from the night shift to the evening shift"
    assert nurse_name("Nurse_08") == "Nurse 08"


def test_who_words_sentence_and_fallbacks():
    def summ(oid, qr, extra, relief):
        return {"id": oid, "new_quick_returns": qr, "extra_work": extra, "relief": relief}
    ours = summ("Option_1", -1, None, {"nurse": "Nurse_59", "before": 18.5, "after": 10.0})
    ortec = summ("Option_2", 1, {"nurse": "Nurse_08", "before": 1.5, "after": 6.0}, None)
    ward = {"tired_at": 10.0, "median_at": 5.0}
    assert who_words(ours, ortec, ward) == ("With the hospital rule, Nurse 59 (recent load: high) is moved off a short rest; today's "
                                            "software would make Nurse 08 (recent load: low) come back after a short rest.")
    assert "recent load: low" in who_words(ours, ortec, {"tired_at": 20.0, "median_at": 20.0})
    assert "Option_" not in who_words(ours, summ("Option_3", 0, None, None))
    assert who_words(summ("Option_1", 0, None, None), ortec) is None
    assert "same fix" in who_words(ours, ours)


def test_ward_context_is_tired_and_tiredness_word():
    assert ward_context({f"N{i}": float(i) for i in range(5)}) == {"tired_at": 3.0, "median_at": 2.0}
    assert ward_context([]) == {"tired_at": None, "median_at": None}
    ctx = {"tired_at": 3.0, "median_at": 2.0}
    assert is_tired(3.0, ctx) and is_tired(4.5, ctx) and not is_tired(2.9, ctx)
    assert not is_tired(5.0, None) and not is_tired(0.0, {"tired_at": 0.0})
    assert [tiredness_word(v, ctx) for v in (3.0, 4.5, 2.0, 2.9, 1.9, 0.0)] == ["high", "high", "medium", "medium", "low", "low"]
    assert tiredness_word(5.0, None) == "low" and tiredness_word(0.0, {"tired_at": 0.0, "median_at": 0.0}) == "low"


def _pick(oid, desc, people):
    return {"id": oid, "description": desc, "people_disturbed": len(people),
            "involved": [{"nurse": n, "before": b, "after": a, "qr_change": q} for n, b, a, q in people],
            "new_quick_returns": sum(p[3] for p in people),
            "relief": next(({"nurse": n, "before": b, "after": a} for n, b, a, q in people if a < b), None),
            "extra_work": None}


def test_card_lines_genai_relief_and_cost():
    ortec = _pick("O1", "Call in Nurse 08 for the day shift", [("Nurse_08", 1.5, 6.0, 1)])
    ours = _pick("O2", "Move Nurse 67 from the day shift to the evening shift; call in Nurse 08 for the day shift",
                 [("Nurse_67", 4.5, 3.0, -1), ("Nurse_09", 1.0, 2.0, 0)])
    ward = {"tired_at": 4.0, "median_at": 1.2}
    cl = card_lines(ours, ortec, ward, {"ours": ["everyone keeps 11 h+ rest ✓"], "ortec": ["Nurse 08 comes back after only 8.5 h rest ⚠️"]})
    assert cl["ortec"] == ["Call in Nurse 08 for the day shift",
                           "Result: Nurse 08 (recent load: medium) gets a short rest.", "Changes 1 person's shift."]
    assert cl["ours"] == [ours["description"], "Result: Nurse 67 (recent load: high) is moved off a short rest.",
                          "Cost: changes 2 people's shifts instead of 1."]
    assert cl["rest_lines"] == {"ours": ["everyone keeps 11 h+ rest ✓"], "ortec": ["Nurse 08 comes back after only 8.5 h rest ⚠️"]}
    assert not any("tiredness 4" in l or "tiredness 1" in l for l in cl["ours"] + cl["ortec"])  # words, not scores
    cl = card_lines(ours, _pick("O1", "x", [("Nurse_70", 0.5, 1.0, 0)]), ward)
    assert cl["ortec"][1] == "Result: no one gets relief." and cl["rest_lines"] == {"ours": [], "ortec": []}


def test_card_lines_same_size_no_cost_and_plain_relief():
    a = _pick("O1", "d1", [("Nurse_01", 2.0, 1.0, 0)])
    b = _pick("O2", "d2", [("Nurse_02", 2.0, 3.0, 0)])
    cl = card_lines(a, b, None)
    assert cl["ours"][0] == "d1" and cl["ours"][1].startswith("Result: Nurse 01 (recent load: low)")
    assert len(cl["ours"]) == 2 and cl["ortec"][-1] == "Changes 1 person's shift."
    two = _pick("O3", "d3", [("Nurse_03", 1.0, 2.0, 0), ("Nurse_04", 1.0, 2.0, 0)])
    assert card_lines(a, two, None)["ortec"][-1] == "Changes 2 people's shifts."


def _ch(nurse, day, old, new):
    return Change(nurse, day, old, new)


def test_rest_lines_new_quick_return_and_restore():
    w = make_ward(n=3, days=14)
    # Nurse_01: E on day 3, off day 4; Nurse_02 works D on day 4. Moving Nurse_01 to D on day 4 -> E then D = 8.5 h.
    r = roster_with(w, {"Nurse_01": {3: "E"}, "Nurse_02": {4: "D"}})
    before = {k: dict(v) for k, v in r.by_nurse.items()}
    opt = Option("Option_1", "direct", (_ch("Nurse_01", 4, None, "D"),))
    assert rest_effect(r, opt.changes) == [{"nurse": "Nurse_01", "before": None, "after": 8.5}]
    assert rest_lines(r, opt) == ["Nurse 01 comes back after only 8.5 h rest ⚠️"]
    assert r.by_nurse == before and r.by_slot[(4, "D")] == {"Nurse_02"}  # roster restored


def test_rest_lines_improvement_and_all_ok():
    w = make_ward(n=3, days=14)
    # Nurse_03 has E (day 3) then D (day 4) = 8.5 h; changing day 4 to E gives 16.5 h.
    r = roster_with(w, {"Nurse_03": {3: "E", 4: "D"}})
    fix = Option("Option_2", "move", (_ch("Nurse_03", 4, "D", "E"),))
    assert rest_lines(r, fix) == ["Nurse 03: rest goes from 8.5 h to 16.5 h ✓"]
    off = Option("Option_3", "move", (_ch("Nurse_03", 4, "D", None),))
    assert rest_lines(r, off) == ["Nurse 03: rest goes from 8.5 h to 11 h+ ✓"]
    fine = roster_with(w, {"Nurse_01": {3: "D"}})
    ok = Option("Option_4", "direct", (_ch("Nurse_01", 4, None, "D"),))
    assert rest_lines(fine, ok) == ["everyone keeps 11 h+ rest ✓"]


def test_rest_lines_worse_when_already_short_and_window():
    w = make_ward(n=2, days=20)
    r = roster_with(w, {"Nurse_01": {3: "N", 4: "E"}, "Nurse_02": {10: "E", 14: "D"}})
    # N on day 3 ends 31.5 h; E on day 4 starts 4*24+15.5 -> 8 h rest; D on day 4 starts at 7.5 -> 0 h rest.
    worse = Option("Option_5", "move", (_ch("Nurse_01", 4, "E", "D"),))
    assert rest_lines(r, worse) == ["Nurse 01: rest drops from 8 h to 0 h ⚠️"]
    # a short rest further than 2 days from the change is not counted
    far = Option("Option_6", "direct", (_ch("Nurse_02", 12, None, "D"),))
    assert rest_lines(r, far) == ["everyone keeps 11 h+ rest ✓"]


def test_difference_text_rest_fixed_made_and_fallbacks():
    from sim.compare import difference_text
    ward = {"tired_at": 4.0, "median_at": 1.2}
    ortec = _pick("O1", "Call in Nurse 36", [("Nurse_36", 0.5, 2.0, 0)])
    ours = _pick("O2", "Move Nurse 05; call in Nurse 36", [("Nurse_05", 2.0, 1.0, -1), ("Nurse_36", 0.5, 2.0, 0)])
    fx = {"ours": [{"nurse": "Nurse_05", "before": 8.0, "after": 16.5}, {"nurse": "Nurse_36", "before": None, "after": 24.0}],
          "ortec": [{"nurse": "Nurse_36", "before": None, "after": 24.0}]}
    assert difference_text(ours, ortec, fx, ward) == ("Today's software leaves Nurse 05 (recent load: medium) with only 8 h rest "
                                                      "between two shifts; the hospital rule changes the plan so they get 16.5 h.")
    fx_made = {"ours": [], "ortec": [{"nurse": "Nurse_36", "before": 30.0, "after": 8.5}]}
    assert difference_text(ours, ortec, fx_made, ward) == ("Today's software would bring Nurse 36 (recent load: low) back after "
                                                           "only 8.5 h rest; the hospital rule avoids that.")
    fx_own = {"ours": [{"nurse": "Nurse_05", "before": None, "after": 8.0}], "ortec": []}
    assert "Note: the hospital rule's fix brings Nurse 05" in difference_text(ours, ortec, fx_own, ward)
    assert difference_text(ours, ours, fx, ward) == "Both chose the same fix here."
    # Both picks give Nurse 36 a short rest: never claim "GenAI avoids that", only the honest note.
    both = {"ortec": [{"nurse": "Nurse_36", "before": 30.0, "after": 8.5}], "ours": [{"nurse": "Nurse_36", "before": 30.0, "after": 8.5}]}
    t = difference_text(ours, ortec, both, ward)
    assert "avoids" not in t and t.startswith("Note: the hospital rule's fix brings Nurse 36")
    # The worst case is named: the shortest rest wins.
    two = {"ours": [], "ortec": [{"nurse": "Nurse_36", "before": None, "after": 10.0}, {"nurse": "Nurse_05", "before": None, "after": 8.0}]}
    assert "Nurse 05" in difference_text(ours, ortec, two, ward) and "8 h" in difference_text(ours, ortec, two, ward)
    a = dict(ortec, extra_work={"nurse": "Nurse_36", "before": 0.5, "after": 2.0})
    b = dict(ours, extra_work={"nurse": "Nurse_05", "before": 4.5, "after": 6.0})
    assert difference_text(b, a, {}, ward) == ("Today's software gives the extra work to Nurse 36 (recent load: low); "
                                               "the hospital rule gives it to Nurse 05 (recent load: medium).")
    assert difference_text(ours, ortec, {}, ward) is None


def test_recent_load_shows_the_counts_behind_it():
    from sim.compare import _who
    assert _who("Nurse_67", 20.0, {"tired_at": 10.0, "median_at": 5.0}, {"QR": 3, "N": 4, "LR": 0, "OT": 0.0, "SN": 1}) == (
        "Nurse 67 (recent load: high, 3 quick returns, 4 nights, 1 short-notice change in the past and next 28 days)")
