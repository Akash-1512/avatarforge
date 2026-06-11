"""Deterministic eval metrics — synthetic payloads, exact expectations."""

from backend.evals import metrics as m
from backend.models.schemas import ScriptPayload, ScriptSegment


def _payload(texts, durations, total=None, title="Title"):
    segs = [
        ScriptSegment(index=i, text=t, est_duration_sec=d)
        for i, (t, d) in enumerate(zip(texts, durations))
    ]
    return ScriptPayload(title=title, segments=segs, total_duration_sec=total or sum(durations))


def test_duration_accuracy_perfect_and_off():
    p = _payload(["Hello there friend."], [10], total=60)
    assert m.duration_accuracy(p, 60) == 1.0
    p2 = _payload(["Hi."], [10], total=30)
    assert m.duration_accuracy(p2, 60) == 0.5


def test_spoken_duration_consistency_detects_gaming():
    # Claims 60s but only ~10 words (~4s of speech) — inconsistent
    p = _payload(["This is only about ten words in total here now."], [60], total=60)
    assert m.spoken_duration_consistency(p, 60) < 0.2


def test_segment_pacing():
    good = _payload(["a b c d e f g h"] * 3, [5, 8, 12])
    assert m.segment_pacing_score(good) == 1.0
    bad = _payload(["x"] * 2, [1, 40])
    assert m.segment_pacing_score(bad) == 0.0


def test_speakability_flags_markdown_urls_emoji():
    clean = _payload(["Just plain spoken text here."], [5])
    assert m.speakability_score(clean) == 1.0
    dirty = _payload(["Check **this** out", "Visit https://x.com", "Nice 🚀"], [5, 5, 5])
    assert m.speakability_score(dirty) == 0.0


def test_structure_score():
    good = _payload(["First.", "Second."], [5, 5])
    assert m.structure_score(good) == 1.0
    bad = ScriptPayload(
        title="",
        total_duration_sec=10,
        segments=[ScriptSegment(index=1, text="Wrong index start", est_duration_sec=5)],
    )
    assert m.structure_score(bad) < 1.0


def test_compute_all_keys():
    p = _payload(["Hello world this is fine."], [10])
    out = m.compute_all(p, 10)
    assert set(out) == {
        "duration_accuracy",
        "spoken_duration_consistency",
        "segment_pacing",
        "speakability",
        "structure",
    }
