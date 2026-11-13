"""Constraint Tracker: natural-language update -> structured ConstraintDiff.

Rule-based parser used by the offline build. It is evaluated on both
template sets (A seen in train, B held out) by ``scripts/check_tracker.py``.
"""

from __future__ import annotations

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

def validate(d: ConstraintDiff, c: Constraints) -> ConstraintDiff:
    """Reject diffs whose op/type/values are outside the schema."""
    from taskflow.env.state import DIFF_OPS, DIFF_TYPES, TRANSPORT_RULES

    if d.op not in DIFF_OPS or d.target_type not in DIFF_TYPES:
        raise ValueError(f"bad op/type {d.op}/{d.target_type}")
    t, new = d.target_type, d.new
    if d.op == "reprioritize" and t != "priority":
        raise ValueError("reprioritize only applies to priority")
    if d.op != "delete":
        ok = {
            "budget": lambda v: float(v) > 0,
            "room_type": lambda v: v in ROOM_TYPES,
            "house_rule": lambda v: v in HOUSE_RULES,
            "cuisine": lambda v: v in CUISINES,
            "transport": lambda v: v in TRANSPORT_RULES,
            "min_rating": lambda v: 0 <= float(v) <= 5,
            "priority": lambda v: v in PRIORITIES,
        }[t]
        if new is None or not ok(new):
            raise ValueError(f"bad value {new!r} for {t}")
    if t == "budget":
        d.new = float(new)
        d.op = "replace"
        d.old = c.budget
    if t == "min_rating" and d.op != "delete":
        d.new = float(new)
    if t == "cuisine" and d.op in ("delete", "replace") and d.old not in c.cuisines:
        raise ValueError(f"cuisine {d.old!r} is not currently required")
    if t == "house_rule" and d.op == "delete" and d.old not in c.house_rules:
        raise ValueError(f"house rule {d.old!r} is not currently required")
    return d


def parse_llm(text: str, c: Constraints, client) -> ConstraintDiff:
    from taskflow.llm.prompts import tracker_prompt

    system, user = tracker_prompt(text, c.to_dict())
    out = client.complete_json(system, user, max_tokens=200)
    if out.get("op") == "none":
        raise ValueError("message does not change any constraint")
    d = ConstraintDiff(op=out.get("op"), target_type=out.get("target_type"), old=out.get("old"),
                       new=out.get("new"), nl=text)
    return validate(d, c)


def parse_any(text: str, c: Constraints, client=None) -> tuple[ConstraintDiff, str]:
    """LLM parse when available, rule-based otherwise. Returns (diff, source)."""
    if client is not None:
        try:
            return parse_llm(text, c, client), "llm"
        except Exception:
            pass
    return parse(text, c), "rules"
