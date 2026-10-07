"""Deterministic display safety net: replace metric codes in model text with plain words."""
from __future__ import annotations

import re

# "N" is also a shift letter, so only rewrite it as a metric: "N 3" or "N shifts".
_RULES = [
    (re.compile(r"\bQR\b"), "quick returns"),
    (re.compile(r"\bSN\b"), "short-notice changes"),
    (re.compile(r"\bLR\b"), "long runs"),
    (re.compile(r"\bOT\b"), "overtime"),
    (re.compile(r"\bN shifts\b"), "night shifts"),
    (re.compile(r"\bN(?= \d)"), "night shifts"),
    (re.compile(r"\bquick_returns\b"), "quick returns"),
    (re.compile(r"\bshort_notice\b"), "short-notice changes"),
    (re.compile(r"\blong_runs\b"), "long runs"),
    (re.compile(r"\bnights\b"), "night shifts"),
    (re.compile(r"\bovertime\b"), "overtime"),
    (re.compile(r"\b(?:strain|load)_before\b"), "load before"),
    (re.compile(r"\b(?:strain|load)_after\b"), "load after"),
    (re.compile(r"\bstrain\b"), "load"),
    (re.compile(r"\bStrain\b"), "Load"),
]


def plainify(s) -> str:
    """Display-only safety net: replace metric codes in model text with plain words.

    Never raises; non-strings come back as an empty string. Ids such as Nurse_10 or Option_2
    and letters inside words are left alone (case-sensitive, word boundaries).
    """
    try:
        if not isinstance(s, str):
            return ""
        for rx, word in _RULES:
            s = rx.sub(word, s)
        return s
    except Exception:
        return s if isinstance(s, str) else ""


_SHIFT_WORDS = {"D": "day shift", "E": "evening shift", "N": "night shift"}
_SHIFT_RX = re.compile(r"(?<=→ )[DEN]\b|\b[DEN](?= →)")

def shift_words(s: str) -> str:
    """'Nurse_02: off → D' -> 'Nurse_02: off → day shift' (display only, never raises)."""
    try:
        return _SHIFT_RX.sub(lambda m: _SHIFT_WORDS[m.group(0)], s)
    except Exception:
        return s if isinstance(s, str) else ""


_SENT_END = re.compile(r"(?<=[.!?])\s+")


def short_text(text, max_sentences: int = 2, max_chars: int = 320):
    """Keep whole leading sentences (at most max_sentences, within max_chars).

    Splits only where a sentence-ending mark is followed by whitespace, so decimals like
    "1.5" stay intact. Returns (short, was_truncated); never raises. The first sentence is
    always kept, even when it alone exceeds max_chars.
    """
    try:
        if not isinstance(text, str):
            return "", False
        text = text.strip()
        sentences = [p for p in _SENT_END.split(text) if p]
        kept, length = [], 0
        for s in sentences[:max_sentences]:
            if kept and length + 1 + len(s) > max_chars:
                break
            kept.append(s)
            length += len(s) + (1 if len(kept) > 1 else 0)
        short = " ".join(kept)
        return short, len(kept) < len(sentences)
    except Exception:
        return (text if isinstance(text, str) else ""), False


_OPTION_RX = re.compile(r"\bOption_0*(\d+)\b", re.I)


def replace_option_ids(s, descriptions: dict) -> str:
    """Display-only backstop: swap any remaining 'Option_N' for its description in quotes.

    descriptions maps option ids ('Option_3') to plain descriptions. Unknown ids become
    'another option'. Never raises; non-strings come back as an empty string.
    """
    try:
        if not isinstance(s, str):
            return ""

        def sub(m):
            d = descriptions.get(f"Option_{int(m.group(1))}")
            return f"“{d}”" if d else "another option"
        return _OPTION_RX.sub(sub, s)
    except Exception:
        return s if isinstance(s, str) else ""


def option_descriptions(payload: dict) -> dict:
    """{option id: description} from a decide/explain payload (options without one are skipped)."""
    try:
        return {o["id"]: o["description"] for o in payload.get("options", []) if o.get("description")}
    except Exception:
        return {}
