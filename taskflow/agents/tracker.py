"""Constraint Tracker: natural-language update -> structured ConstraintDiff.

``parse``: rule-based parser used offline (covers both template sets; see
tests/test_pipeline.py). It raises ValueError, and only ValueError, when it
cannot read a message.

``parse_llm`` / ``parse_any``: LLM parser with schema validation. An explicit
"no change" reply is a result (``None``), not an error, and is never re-read
by the rules. Fatal client errors (bad key/model/endpoint) propagate.
"""

from __future__ import annotations

import math
import re

from taskflow.env.state import (CUISINES, HOUSE_RULES, PRIORITIES, ROOM_TYPES, ConstraintDiff,
                                Constraints)

NEG = re.compile(r"\b(no longer|doesn't matter|don't matter|not required|forget|drop|"
                 r"no particular|any kind|any transportation|every transportation|"
                 r"is no longer|not a concern|fine now|open to)\b", re.I)


def parse(text: str, c: Constraints) -> ConstraintDiff:
    t = text.strip()
    low = t.lower()
    neg = bool(NEG.search(low))

    m = re.search(r"\$\s?([\d,]+(?:\.\d+)?)", t)
    if m and re.search(r"budget|limit|total|spend", low):
        return ConstraintDiff("replace", "budget", c.budget, float(m.group(1).replace(",", "")), nl=t)

    if re.search(r"\bpriority\b", low) and neg:
        return ConstraintDiff("delete", "priority", c.priority, None, nl=t)
    for p in PRIORITIES:
        if re.search(rf"\b(optimize for|{p} matters)\b", low) and p in low:
            return ConstraintDiff("reprioritize", "priority", c.priority, p, nl=t)

    # Longest alternative first so "not shared room" is not read as "shared room".
    room_re = "|".join(re.escape(r) for r in sorted(ROOM_TYPES, key=len, reverse=True))
    positions = [m.group(0) for m in re.finditer(room_re, low)]
    if positions or re.search(r"room type|kind of room", low):
        if neg and not positions:
            return ConstraintDiff("delete", "room_type", c.room_type, None, nl=t)
        if not positions:
            raise ValueError(f"room type mentioned but no value given: {t!r}")
        new = positions[-1]
        if c.room_type and len(positions) > 1:
            return ConstraintDiff("replace", "room_type", positions[0], new, nl=t)
        return ConstraintDiff("add" if c.room_type is None else "replace", "room_type",
                              c.room_type, new, nl=t)

    for h in HOUSE_RULES:
        if h in low and re.search(r"allow|permit", low):
            if neg:
                return ConstraintDiff("delete", "house_rule", h, None, nl=t)
            return ConstraintDiff("add", "house_rule", None, h, nl=t)

    if re.search(r"rating|rated", low) and re.search(r"restaurant", low):
        if neg:
            return ConstraintDiff("delete", "min_rating", c.min_rating, None, nl=t)
        r = re.search(r"(\d(?:\.\d)?)", t)
        if r is None:
            raise ValueError(f"rating mentioned but no number given: {t!r}")
        return ConstraintDiff("add", "min_rating", None, float(r.group(1)), nl=t)

    if "no flight" in low or "no self-driving" in low:
        return ConstraintDiff("add", "transport", None,
                              "no flight" if "no flight" in low else "no self-driving", nl=t)
    if re.search(r"transportation", low) and neg:
        return ConstraintDiff("delete", "transport", c.transport, None, nl=t)

    cus = sorted([cu for cu in CUISINES if cu.lower() in low], key=lambda x: low.find(x.lower()))
    if cus:
        if len(cus) >= 2:
            return ConstraintDiff("replace", "cuisine", cus[0], cus[1], nl=t)
        if neg:
            return ConstraintDiff("delete", "cuisine", cus[0], None, nl=t)
        return ConstraintDiff("add", "cuisine", None, cus[0], nl=t)

    raise ValueError(f"tracker could not parse: {t!r}")


# --------------------------------------------------------------------------
# LLM-backed tracker (used when a client is configured; falls back to parse)
# --------------------------------------------------------------------------

ALLOWED_OPS = {
    "budget": {"replace"},
    "room_type": {"add", "replace", "delete"},
    "house_rule": {"add", "delete"},
    "cuisine": {"add", "replace", "delete"},
    "transport": {"add", "replace", "delete"},
    "min_rating": {"add", "replace", "delete"},
    "priority": {"reprioritize", "delete"},
}
SINGLE_VALUED = {"room_type": "room_type", "transport": "transport", "min_rating": "min_rating",
                 "priority": "priority"}


def validate(d: ConstraintDiff, c: Constraints) -> ConstraintDiff:
    """Enforce the op/type matrix and old-value semantics; raise ValueError otherwise.

    Harmless op spellings are normalized (e.g. "add budget" -> replace,
    "add priority" -> reprioritize, "add room_type" when one is set -> replace).
    """
    from taskflow.env.state import DIFF_TYPES, TRANSPORT_RULES

    t = d.target_type
    if t not in DIFF_TYPES:
        raise ValueError(f"unknown target_type {t!r}")
    if t == "budget" and d.op in ("add", "replace"):
        d.op = "replace"
    if t == "priority" and d.op in ("add", "replace"):
        d.op = "reprioritize"
    if t in ("room_type", "transport", "min_rating") and d.op == "add" and getattr(c, SINGLE_VALUED[t]) is not None:
        d.op = "replace"
    if d.op not in ALLOWED_OPS[t]:
        raise ValueError(f"op {d.op!r} not allowed for {t}")

    if d.op != "delete":
        ok = {
            "budget": lambda v: math.isfinite(float(v)) and float(v) > 0,
            "room_type": lambda v: v in ROOM_TYPES,
            "house_rule": lambda v: v in HOUSE_RULES,
            "cuisine": lambda v: v in CUISINES,
            "transport": lambda v: v in TRANSPORT_RULES,
            "min_rating": lambda v: math.isfinite(float(v)) and 0 <= float(v) <= 5,
            "priority": lambda v: v in PRIORITIES,
        }[t]
        try:
            good = d.new is not None and ok(d.new)
        except (TypeError, ValueError):
            good = False
        if not good:
            raise ValueError(f"bad value {d.new!r} for {t}")

    # Old-value semantics: "old" must describe the current state.
    if t == "budget":
        d.new, d.old = float(d.new), c.budget
    elif t in SINGLE_VALUED:
        cur = getattr(c, SINGLE_VALUED[t])
        if d.op == "delete" and cur is None:
            raise ValueError(f"no {t} to delete")
        d.old = cur
        if t == "min_rating" and d.op != "delete":
            d.new = float(d.new)
        if d.op != "delete" and d.new == cur:
            raise ValueError(f"{t} is already {cur!r}")
    elif t == "house_rule":
        if d.op == "delete":
            if d.old not in c.house_rules:
                raise ValueError(f"house rule {d.old!r} is not currently required")
            d.new = None
        else:
            if d.new in c.house_rules:
                raise ValueError(f"house rule {d.new!r} already required")
            d.old = None
    elif t == "cuisine":
        if d.op in ("delete", "replace") and d.old not in c.cuisines:
            raise ValueError(f"cuisine {d.old!r} is not currently required")
        if d.op in ("add", "replace") and d.new in c.cuisines:
            raise ValueError(f"cuisine {d.new!r} already required")
        if d.op == "add":
            d.old = None
        if d.op == "delete":
            d.new = None
    return d


def parse_llm(text: str, c: Constraints, client) -> ConstraintDiff | None:
    """LLM parse. Returns None for an explicit "no change"; raises on invalid replies."""
    from taskflow.llm.prompts import tracker_prompt

    system, user = tracker_prompt(text, c.to_dict())
    out = client.complete_json(system, user, max_tokens=200)
    if out.get("op") == "none":
        return None
    d = ConstraintDiff(op=out.get("op"), target_type=out.get("target_type"), old=out.get("old"),
                       new=out.get("new"), nl=text)
    return validate(d, c)


def parse_any(text: str, c: Constraints, client=None) -> tuple[ConstraintDiff | None, str]:
    """Returns (diff or None, source) with source in {"llm", "llm-none", "rules"}.

    Rules are used only when there is no client or the LLM reply was unusable
    (recorded as a fallback). An explicit "no change" is respected.
    """
    from taskflow.llm.client import LLMFatalError, note_fallback

    if client is not None:
        try:
            d = parse_llm(text, c, client)
            return (d, "llm") if d is not None else (None, "llm-none")
        except LLMFatalError:
            raise
        except Exception as e:  # malformed JSON, schema violation, transient error
            note_fallback(client, "tracker", f"{type(e).__name__}: {e}")
    return parse(text, c), "rules"
