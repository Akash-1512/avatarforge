"""The self-correcting quality loop: render -> judge -> re-render, bounded by caps."""

import pytest

from backend.services.quality.judge import QualityJudge, Verdict
from backend.services.quality.loop import QualityLoop
from backend.services.scene.service import SceneService


class _Engine:
    name = "sora2"
    accepts_real_face = False

    def __init__(self):
        self.calls = 0

    async def generate(self, prompt, seconds=4, size="1280x720"):
        self.calls += 1
        return f"CLIP{self.calls}".encode()


class _Judge:
    """Returns a scripted sequence of scores; no real vision/FFmpeg."""

    def __init__(self, scores):
        self._scores = list(scores)
        self.calls = 0

    async def judge(self, video_bytes, intended):
        self.calls += 1
        s = self._scores.pop(0) if self._scores else 1.0
        return Verdict(score=s, issues=([] if s >= 0.75 else ["off-style"]), suggestion="more neon")


def _svc():
    return SceneService(engines={"sora2": _Engine()}, default_engine="sora2")


@pytest.mark.asyncio
async def test_passes_on_first_try_no_rerender():
    eng = _Engine()
    loop = QualityLoop(SceneService(engines={"sora2": eng}), _Judge([0.9]), threshold=0.75)
    r = await loop.run("a neon fox", seconds=4)
    assert r.passed and r.iterations == 1 and eng.calls == 1


@pytest.mark.asyncio
async def test_rerenders_until_pass():
    eng = _Engine()
    loop = QualityLoop(
        SceneService(engines={"sora2": eng}),
        _Judge([0.4, 0.6, 0.85]),
        threshold=0.75,
        max_iterations=3,
    )
    r = await loop.run("a neon fox", seconds=4)
    assert r.passed and r.iterations == 3 and eng.calls == 3
    assert r.best_score == 0.85


@pytest.mark.asyncio
async def test_iteration_cap_stops_loop():
    eng = _Engine()
    loop = QualityLoop(
        SceneService(engines={"sora2": eng}),
        _Judge([0.1, 0.2, 0.3, 0.4]),
        threshold=0.75,
        max_iterations=2,
    )
    r = await loop.run("hard scene", seconds=4)
    assert not r.passed and r.iterations == 2 and eng.calls == 2  # capped at 2
    assert r.best_score == 0.2  # best of the two


@pytest.mark.asyncio
async def test_cost_cap_stops_loop():
    eng = _Engine()
    # 8s sora2 = $0.80/render; cap at $1.0 allows only the first render
    loop = QualityLoop(
        SceneService(engines={"sora2": eng}),
        _Judge([0.1, 0.1, 0.1]),
        threshold=0.75,
        max_iterations=5,
        max_cost_usd=1.0,
    )
    r = await loop.run("expensive scene", seconds=8)
    assert eng.calls == 1 and not r.passed  # second render would breach the cap
    assert r.est_cost_usd <= 1.0


@pytest.mark.asyncio
async def test_returns_best_attempt_when_none_pass():
    loop = QualityLoop(_svc(), _Judge([0.5, 0.7, 0.55]), threshold=0.9, max_iterations=3)
    r = await loop.run("x", seconds=4)
    assert not r.passed and r.best_score == 0.7 and len(r.attempts) == 3


def test_judge_degrades_to_pass_without_endpoint(monkeypatch):
    from backend.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "azure_openai_endpoint", "", raising=False)
    monkeypatch.setattr(s, "azure_openai_api_key", "", raising=False)
    assert QualityJudge(s).configured() is False


def test_judge_parse_handles_garbage():
    v = QualityJudge.__dict__["_parse"]("not json")
    assert v.passed and v.score == 1.0


def test_judge_parse_reads_verdict():
    v = QualityJudge.__dict__["_parse"]('{"score":0.42,"issues":["a","b"],"suggestion":"fix"}')
    assert v.score == 0.42 and v.issues == ["a", "b"] and v.suggestion == "fix"
