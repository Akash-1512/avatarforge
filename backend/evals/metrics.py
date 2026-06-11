"""Deterministic script-quality metrics — fast, free, no LLM needed.

These catch structural regressions instantly: a prompt change that breaks
duration targeting, produces unspeakable text, or degrades pacing fails
here before any judge is consulted.
"""

import re
from typing import Dict

from backend.models.schemas import ScriptPayload

# Average speaking rate; consistent with the generation prompt's guidance.
WORDS_PER_SECOND = 2.5

_UNSPEAKABLE = re.compile(r"[#*_`>\[\]{}|<>]|http[s]?://|\n-")
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]")


def duration_accuracy(payload: ScriptPayload, target_sec: int) -> float:
    """1.0 = perfect match; 0.0 = off by 100%+ from target."""
    if target_sec <= 0:
        return 0.0
    err = abs(payload.total_duration_sec - target_sec) / target_sec
    return max(0.0, 1.0 - err)


def estimated_spoken_duration_sec(payload: ScriptPayload) -> float:
    words = sum(len(seg.text.split()) for seg in payload.segments)
    return round(words / WORDS_PER_SECOND, 1)


def spoken_duration_consistency(payload: ScriptPayload, target_sec: int) -> float:
    """Does the actual word count support the claimed duration? (anti-gaming check)"""
    if target_sec <= 0:
        return 0.0
    est = estimated_spoken_duration_sec(payload)
    err = abs(est - target_sec) / target_sec
    return max(0.0, 1.0 - err)


def segment_pacing_score(payload: ScriptPayload) -> float:
    """Share of segments within a speakable 3-20s range."""
    if not payload.segments:
        return 0.0
    ok = sum(1 for s in payload.segments if 3 <= s.est_duration_sec <= 20)
    return ok / len(payload.segments)


def speakability_score(payload: ScriptPayload) -> float:
    """Share of segments free of unspeakable artifacts (markdown, URLs, emoji)."""
    if not payload.segments:
        return 0.0
    clean = sum(
        1 for s in payload.segments if not _UNSPEAKABLE.search(s.text) and not _EMOJI.search(s.text)
    )
    return clean / len(payload.segments)


def structure_score(payload: ScriptPayload) -> float:
    """Basic shape: has title, 1+ segments, contiguous indices, non-empty text."""
    checks = [
        bool(payload.title and payload.title.strip()),
        len(payload.segments) >= 1,
        all(s.text.strip() for s in payload.segments),
        [s.index for s in payload.segments] == list(range(len(payload.segments))),
    ]
    return sum(checks) / len(checks)


def compute_all(payload: ScriptPayload, target_sec: int) -> Dict[str, float]:
    return {
        "duration_accuracy": round(duration_accuracy(payload, target_sec), 3),
        "spoken_duration_consistency": round(spoken_duration_consistency(payload, target_sec), 3),
        "segment_pacing": round(segment_pacing_score(payload), 3),
        "speakability": round(speakability_score(payload), 3),
        "structure": round(structure_score(payload), 3),
    }
