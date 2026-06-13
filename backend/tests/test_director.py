"""Director: brief -> storyboard, with parse, clamp, and fallback behavior."""

import json

import pytest

from backend.services.director.service import (
    MAX_SCENES,
    MAX_TOTAL_SECONDS,
    DirectorError,
    DirectorService,
)


class _FakeLLM:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    async def complete_json_raw(self, system, user):
        self.calls += 1
        return self._responses.pop(0) if self._responses else "{}"


def _board_json(n_scenes=3, seconds=5, style="anime"):
    return json.dumps(
        {
            "title": "Test Film",
            "style": style,
            "scenes": [
                {"shot": f"scene {i}", "camera": "static", "dialogue": "", "seconds": seconds}
                for i in range(n_scenes)
            ],
        }
    )


@pytest.mark.asyncio
async def test_storyboard_parses():
    d = DirectorService(_FakeLLM(_board_json(3)))
    b = await d.storyboard("a short film about a fox")
    assert b.title == "Test Film" and b.style == "anime" and len(b.scenes) == 3


@pytest.mark.asyncio
async def test_scene_count_clamped():
    d = DirectorService(_FakeLLM(_board_json(20, seconds=2)))
    b = await d.storyboard("epic")
    assert len(b.scenes) <= MAX_SCENES


@pytest.mark.asyncio
async def test_total_runtime_clamped():
    d = DirectorService(_FakeLLM(_board_json(8, seconds=10)))  # 80s -> must trim to <=60
    b = await d.storyboard("long")
    assert b.total_seconds <= MAX_TOTAL_SECONDS


@pytest.mark.asyncio
async def test_per_scene_seconds_clamped():
    d = DirectorService(_FakeLLM(_board_json(2, seconds=99)))
    b = await d.storyboard("x")
    assert all(2 <= s.seconds <= 10 for s in b.scenes)


@pytest.mark.asyncio
async def test_style_override():
    d = DirectorService(_FakeLLM(_board_json(2, style="anime")))
    b = await d.storyboard("x", style="pixar")
    assert b.style == "pixar"


@pytest.mark.asyncio
async def test_retry_then_fail_on_garbage():
    llm = _FakeLLM("not json", "still not json")
    d = DirectorService(llm)
    with pytest.raises(DirectorError):
        await d.storyboard("x")
    assert llm.calls == 2  # one attempt + one structured retry
