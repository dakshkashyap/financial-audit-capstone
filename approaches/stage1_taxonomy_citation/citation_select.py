"""Shrink a short grounded ASC list to one full paragraph.

The taxonomy often attaches several refs to one concept: a vague topic
(``230``) plus a real paragraph (``230-10-45-13``). Stage 2 should pick the
paragraph. This module never invents a code that is not already in the list.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

_ASC_STRIP = re.compile(r"^(?:FASB\s+)?ASC\s+", re.I)

# Numerical / value errors → measurement & recognition, not face-of-statement 210/220/230.
_MEASUREMENT = {
    "310", "320", "323", "325", "326", "330", "340", "350", "360",
    "410", "420", "430", "440", "450", "460", "470", "480",
    "605", "606", "610", "705", "710", "712", "715", "718", "720", "730", "740",
    "805", "810", "815", "820", "825", "835", "840", "842", "848", "860",
}
# Wrong bucket / missing line → how the statement is presented.
_PRESENTATION = {"205", "210", "220", "225", "230", "235", "260", "270", "275", "505"}
# Extra fabricated line → recognition of the bogus caption.
_RECOGNITION = {
    "330", "350", "360", "450", "605", "606", "610", "720", "730", "740", "842",
}


def norm_asc(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    s = _ASC_STRIP.sub("", str(text).strip())
    s = s.replace("FASB ", "").strip()
    if not s:
        return None
    m = re.match(r"(\d{3}(?:-[A-Z]?\d+[A-Z]?)*)", s, re.I)
    return m.group(1).upper() if m else None


def topic_of(code: Optional[str]) -> Optional[str]:
    n = norm_asc(code)
    return n.split("-")[0] if n else None


def specificity(code: Optional[str]) -> int:
    """Higher = closer to a full paragraph. S99 staff refs rank below real paras."""
    n = norm_asc(code)
    if not n:
        return 0
    parts = n.split("-")
    staff = any(p.startswith("S") for p in parts)
    return len(parts) * 10 + (0 if staff else 3)


def uniq_full(codes: Iterable[Optional[str]], limit: int = 8) -> List[str]:
    """Dedupe, drop empty, put the most complete codes first, cap the list."""
    seen = []
    have = set()
    for raw in codes:
        n = norm_asc(raw)
        if not n or n in have:
            continue
        have.add(n)
        seen.append(n)
    seen.sort(key=lambda c: (specificity(c), c), reverse=True)
    return seen[:limit]


def preferred_topics(error_type: Optional[str]) -> set:
    et = (error_type or "").strip().lower()
    if et == "numerical error":
        return set(_MEASUREMENT)
    if et in ("misclassification", "missing row"):
        return set(_PRESENTATION)
    if et == "redundant row":
        return set(_RECOGNITION)
    return set()


def pick_primary(candidates: Sequence[str], error_type: Optional[str] = None) -> Optional[str]:
    """Choose one full code from the grounded list (no invention)."""
    pool = uniq_full(candidates, limit=20)
    if not pool:
        return None
    pref = preferred_topics(error_type)
    if pref:
        narrowed = [c for c in pool if topic_of(c) in pref]
        if narrowed:
            pool = narrowed
    no_staff = [c for c in pool if not any(p.startswith("S") for p in c.split("-"))]
    if no_staff:
        pool = no_staff
    general = []
    for c in pool:
        try:
            if int(topic_of(c) or 9999) < 800:
                general.append(c)
        except ValueError:
            continue
    if general:
        pool = general
    return max(pool, key=lambda c: (specificity(c), c))


def snap_citation(
    predicted: Optional[str],
    candidates: Sequence[str],
    error_type: Optional[str] = None,
) -> Optional[str]:
    """Map a model string onto the candidate list (topic → best full paragraph).

    Exact full match wins. A vague ``ASC 230`` becomes the most specific
    ``230-…`` still in the list. Codes the list does not contain are dropped
    (we do not let the model invent a paragraph).
    """
    pool = uniq_full(candidates, limit=20)
    if not pool:
        return None
    pred = norm_asc(predicted)
    if not pred:
        return pick_primary(pool, error_type)

    # Vague "230" must lose to "230-10-45-13" on the same list.
    prefixed = [c for c in pool if c == pred or c.startswith(pred + "-")]
    if prefixed:
        return pick_primary(prefixed, error_type)

    # Predicted is more specific than anything we have (invented tail) → keep
    # the grounded prefix if one candidate is a prefix of the prediction.
    grounded_prefix = [c for c in pool if pred == c or pred.startswith(c + "-")]
    if grounded_prefix:
        return pick_primary(grounded_prefix, error_type)

    same_topic = [c for c in pool if topic_of(c) == topic_of(pred)]
    if same_topic:
        return pick_primary(same_topic, error_type)

    return pick_primary(pool, error_type)


if __name__ == "__main__":
    cands = ["230", "230-10-45", "230-10-45-13", "210-10-S99-1"]
    assert snap_citation("ASC 230", cands) == "230-10-45-13"
    assert snap_citation("ASC 230-10-45-13", cands) == "230-10-45-13"
    assert pick_primary(cands, "Numerical Error") == "230-10-45-13"
    num = ["210-10-S99-1", "330-10-35-1", "330-10-35"]
    assert pick_primary(num, "Numerical Error") == "330-10-35-1"
    assert pick_primary(num, "Misclassification") == "210-10-S99-1"
    print("citation_select ok")
