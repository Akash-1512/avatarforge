"""Deterministic metrics for the planner agent.

These score a produced VideoPlan against the case's expectations without an LLM
in the loop — so they're fast, free, and stable enough to gate on. They measure
the property that actually matters for a constrained agent: it must always
produce an in-spec plan, clamping or defaulting rather than emitting illegal
values or crashing.
"""

from typing import Dict

from backend.models.schemas import VideoPlan

_ALLOWED_TONES = {"professional", "casual", "enthusiastic", "formal", "friendly"}


def in_spec_score(plan: VideoPlan) -> float:
    """1.0 if every field is within the schema's allowed set/bounds, else 0.0.

    A VideoPlan that parsed is already valid by construction, but this guards
    against future schema drift and documents the invariant explicitly.
    """
    ok = (
        plan.tone in _ALLOWED_TONES
        and 15 <= plan.duration_seconds <= 300
        and 2 <= len(plan.language) <= 5
    )
    return 1.0 if ok else 0.0


def duration_in_range_score(plan: VideoPlan, lo: int, hi: int) -> float:
    """1.0 if the planned duration honours the brief's implied range (after
    the schema clamps absurd requests). Measures faithfulness to intent."""
    return 1.0 if lo <= plan.duration_seconds <= hi else 0.0


def tone_match_score(plan: VideoPlan, expected: str | None) -> float:
    """1.0 if the tone matches the brief (when the brief implies one). When no
    specific tone is expected, any allowed tone scores 1.0 — the test is that
    the agent didn't invent an illegal one."""
    if expected is None:
        return 1.0 if plan.tone in _ALLOWED_TONES else 0.0
    return 1.0 if plan.tone == expected else 0.0


def compute_all(plan: VideoPlan, lo: int, hi: int, expected_tone: str | None) -> Dict[str, float]:
    return {
        "plan_in_spec": in_spec_score(plan),
        "plan_duration_in_range": duration_in_range_score(plan, lo, hi),
        "plan_tone_match": tone_match_score(plan, expected_tone),
    }
