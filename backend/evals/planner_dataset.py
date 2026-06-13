"""Evaluation dataset for the planner agent.

The planner turns a free-text brief into a validated VideoPlan. These cases
probe both normal use and the adversarial edges where a model tends to drift:
briefs that imply out-of-range durations, contradictory tones, or values the
schema must clamp. A good plan is in-spec (tone in the allowed set, duration
within bounds, language well-formed) and faithful to the brief's intent.
"""

from typing import List, Optional, TypedDict


class PlannerCase(TypedDict):
    case_id: str
    brief: str
    expect_tone: Optional[str]  # None = don't assert a specific tone
    expect_duration_range: tuple  # (min, max) inclusive bounds the plan must satisfy


PLANNER_DATASET: List[PlannerCase] = [
    {
        "case_id": "plan-normal-01",
        "brief": "A friendly 30-second intro explaining what our analytics product does.",
        "expect_tone": "friendly",
        "expect_duration_range": (15, 60),
    },
    {
        "case_id": "plan-normal-02",
        "brief": "Professional one-minute overview of GDPR compliance for new hires.",
        "expect_tone": "professional",
        "expect_duration_range": (45, 75),
    },
    {
        "case_id": "plan-enthusiastic-03",
        "brief": "Hype up our hackathon launch, high energy, about 20 seconds.",
        "expect_tone": "enthusiastic",
        "expect_duration_range": (15, 30),
    },
    {
        "case_id": "plan-adversarial-toolong",
        "brief": "Give me an exhaustive 30-minute deep dive on distributed consensus.",
        "expect_tone": None,
        "expect_duration_range": (15, 300),  # must clamp to schema max (300), not 1800
    },
    {
        "case_id": "plan-adversarial-tooshort",
        "brief": "A 2-second flash, blink and you miss it.",
        "expect_tone": None,
        "expect_duration_range": (15, 300),  # must lift to schema min (15)
    },
    {
        "case_id": "plan-language-hindi",
        "brief": "Explain UPI payments in Hindi, casual tone, about 40 seconds.",
        "expect_tone": "casual",
        "expect_duration_range": (30, 60),
    },
    {
        "case_id": "plan-vague",
        "brief": "Something about our company.",
        "expect_tone": None,
        "expect_duration_range": (15, 300),  # must still produce a valid in-spec plan
    },
    {
        "case_id": "plan-contradictory",
        "brief": "A very formal but also super casual fun serious video.",
        "expect_tone": None,  # any allowed tone is fine; must not crash or invent one
        "expect_duration_range": (15, 300),
    },
]
