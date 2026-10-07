import pytest

from llm.plain import plainify, shift_words


@pytest.mark.parametrize("src,want", [
    ("adds 1 to QR and 1 to SN for Nurse_68", "adds 1 to quick returns and 1 to short-notice changes for Nurse_68"),
    ("LR rises", "long runs rises"),
    ("OT 2→3", "overtime 2→3"),
    ("Nurse_01 N 3→4", "Nurse_01 night shifts 3→4"),
    ("more N shifts for her", "more night shifts for her"),
    ("trade-off: quick_returns, short_notice, long_runs, nights, overtime",
     "trade-off: quick returns, short-notice changes, long runs, night shift"+"s, overtime"),
    ("more strain on her; Strain up", "more load on her; Load up"),
    ("Nurse_10 works Option_2 and Option_3", "Nurse_10 works Option_2 and Option_3"),
    ("Nurse_02: off → N", "Nurse_02: off → N"),
    ("N for Nurse_5; NOW and ANN stay", "N for Nurse_5; NOW and ANN stay"),
    ("QRS and SNOT stay", "QRS and SNOT stay"),
    ("qr lower-case stays", "qr lower-case stays"),
])
def test_plainify_cases(src, want):
    assert plainify(src) == want


@pytest.mark.parametrize("junk", [None, 5, [], {}, b"QR", object()])
def test_plainify_never_raises_on_junk(junk):
    assert plainify(junk) == ""


def test_shift_words():
    assert shift_words("Nurse_69: E → D; Nurse_10: off → E") == "Nurse_69: evening shift → day shift; Nurse_10: off → evening shift"
    assert shift_words("Nurse_02: off → D; Nurse_03: N → off") == "Nurse_02: off → day shift; Nurse_03: night shift → off"
    assert shift_words(None) == ""


from llm.plain import short_text


def test_short_text_keeps_decimals():
    t = "Nurse_1 gets 1.5 more hours. Option_2 adds 2.25 load! Third sentence here."
    assert short_text(t) == ("Nurse_1 gets 1.5 more hours. Option_2 adds 2.25 load!", True)


def test_short_text_fewer_sentences_than_limit():
    assert short_text("Only one sentence.") == ("Only one sentence.", False)
    assert short_text("One. Two?") == ("One. Two?", False)
    assert short_text("") == ("", False)
    assert short_text(None) == ("", False)


def test_short_text_long_text_respects_chars_and_sentences():
    s = "Word " * 40 + "end."          # ~204 chars
    out, trunc = short_text(f"{s} {s} {s}")
    assert out == s and trunc           # second sentence would exceed 320 chars
    out2, trunc2 = short_text("A. B. C. D.", max_sentences=3)
    assert out2 == "A. B. C." and trunc2
    huge = "x" * 500 + ". Next."
    assert short_text(huge) == ("x" * 500 + ".", True)  # first sentence always kept


def test_plainify_load_field_names():
    from llm.plain import plainify
    assert plainify("strain_before 3 and load_after 4; load_before 1, strain_after 2; strain up") == \
        "load before 3 and load after 4; load before 1, load after 2; load up"


def test_replace_option_ids_backstop():
    from llm.plain import replace_option_ids
    d = {"Option_3": "Call in Nurse 08 for the day shift", "Option_30": "other"}
    assert replace_option_ids("Option_3 beats option 4.", d) == "\u201cCall in Nurse 08 for the day shift\u201d beats option 4."
    assert replace_option_ids("It takes option 2 hours.", d) == "It takes option 2 hours."
    assert replace_option_ids("Option_9 is odd", d) == "another option is odd"
    assert replace_option_ids("Option_30!", d) == "\u201cother\u201d!"
    assert replace_option_ids(None, d) == ""
