"""Evaluation dataset for script generation.

Deliberately diverse: tones, durations, technical vs casual topics, and
edge cases (very short duration, niche topics). Each case is what a real
user would submit. Extend freely — the runner picks up new cases.
"""

from typing import List, TypedDict


class EvalCase(TypedDict):
    case_id: str
    topic: str
    tone: str
    duration_seconds: int


DATASET: List[EvalCase] = [
    {
        "case_id": "tech-01",
        "topic": "How password managers keep you safe",
        "tone": "professional",
        "duration_seconds": 60,
    },
    {
        "case_id": "tech-02",
        "topic": "What is Kubernetes in plain words",
        "tone": "casual",
        "duration_seconds": 45,
    },
    {
        "case_id": "health-01",
        "topic": "One reason morning walks improve focus",
        "tone": "casual",
        "duration_seconds": 15,
    },
    {
        "case_id": "health-02",
        "topic": "Why sleep matters more than coffee",
        "tone": "friendly",
        "duration_seconds": 30,
    },
    {
        "case_id": "biz-01",
        "topic": "Three tips for better client emails",
        "tone": "professional",
        "duration_seconds": 60,
    },
    {
        "case_id": "biz-02",
        "topic": "Why small businesses should track cash flow weekly",
        "tone": "formal",
        "duration_seconds": 90,
    },
    {
        "case_id": "edu-01",
        "topic": "The water cycle explained for kids",
        "tone": "enthusiastic",
        "duration_seconds": 45,
    },
    {
        "case_id": "edu-02",
        "topic": "How compound interest grows your savings",
        "tone": "friendly",
        "duration_seconds": 60,
    },
    {
        "case_id": "edge-short",
        "topic": "Drink more water",
        "tone": "casual",
        "duration_seconds": 15,
    },
    {
        "case_id": "edge-long",
        "topic": "A complete beginner guide to home composting",
        "tone": "professional",
        "duration_seconds": 180,
    },
    {
        "case_id": "edge-niche",
        "topic": "Why mechanical keyboards use different switch types",
        "tone": "enthusiastic",
        "duration_seconds": 60,
    },
    {
        "case_id": "edge-india",
        "topic": "How UPI changed everyday payments in India",
        "tone": "professional",
        "duration_seconds": 60,
    },
]
