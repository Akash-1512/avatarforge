"""Self-correcting quality loop — the centrepiece.

Render a scene, judge the result against its intended description, and if it falls
short, fold the judge's suggestion into the prompt and re-render — repeating until
it passes the quality threshold or hits a hard cap on iterations and spend. Every
attempt is recorded (score, issues, cost) so the whole loop is inspectable in the
trace, and the best attempt is always returned even if none cleared the bar.

The caps are not optional: generative renders cost real money and the Sora 2 preview
quota is tiny, so a runaway loop must be impossible by construction. Iterations and
estimated spend are both bounded, and the loop stops the instant either is reached.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from backend.observability.logging import get_logger
from backend.services.quality.judge import QualityJudge, Verdict, get_quality_judge
from backend.services.scene.service import SceneRequest, SceneService
from backend.services.scene.sora2_client import SceneEngineError, snap_seconds

logger = get_logger(__name__)

# per-second prices used only to estimate spend for the cost cap (not billing).
_ENGINE_COST_PER_SEC = {"sora2": 0.10, "kling": 0.112}
_DEFAULT_COST_PER_SEC = 0.10


@dataclass
class Attempt:
    iteration: int
    engine: str
    prompt: str
    score: float
    issues: List[str]
    est_cost_usd: float


@dataclass
class LoopResult:
    clip: bytes
    passed: bool
    best_score: float
    iterations: int
    est_cost_usd: float
    attempts: List[Attempt] = field(default_factory=list)


class QualityLoop:
    def __init__(
        self,
        scenes: SceneService,
        judge: QualityJudge,
        threshold: float = 0.75,
        max_iterations: int = 3,
        max_cost_usd: float = 2.0,
    ):
        self.scenes = scenes
        self.judge = judge
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.max_cost_usd = max_cost_usd

    def _est_cost(self, engine: str, seconds: int) -> float:
        return _ENGINE_COST_PER_SEC.get(engine, _DEFAULT_COST_PER_SEC) * seconds

    async def run(
        self,
        intended: str,
        seconds: int = 4,
        has_real_face: bool = False,
        engine: Optional[str] = None,
    ) -> LoopResult:
        """Render -> judge -> (maybe) re-render with feedback, until pass or cap."""
        base_prompt = intended
        attempts: List[Attempt] = []
        spent = 0.0
        best: Optional[tuple[bytes, Verdict]] = None

        for i in range(1, self.max_iterations + 1):
            prompt = base_prompt
            if attempts and attempts[-1].issues:
                # fold the previous verdict's suggestion into the next render
                prompt = f"{base_prompt}. Improve: {self._last_suggestion}"

            req = SceneRequest(
                prompt=prompt,
                seconds=seconds,
                has_real_face_reference=has_real_face,
                engine=engine,
            )
            engine_name = self.scenes.route(req)
            cost = self._est_cost(engine_name, snap_seconds(seconds))

            # cost cap: never start a render that would exceed the budget
            if spent + cost > self.max_cost_usd and attempts:
                logger.info("quality_loop_cost_cap", spent=round(spent, 3), next=round(cost, 3))
                break

            try:
                clip = await self.scenes.generate(req)
            except SceneEngineError:
                if attempts:  # keep the best we already have
                    break
                raise

            spent += cost
            verdict = await self.judge.judge(clip, intended)
            self._last_suggestion = verdict.suggestion
            attempts.append(
                Attempt(
                    iteration=i,
                    engine=engine_name,
                    prompt=prompt,
                    score=verdict.score,
                    issues=verdict.issues,
                    est_cost_usd=round(cost, 3),
                )
            )
            logger.info(
                "quality_loop_attempt",
                iteration=i,
                engine=engine_name,
                score=round(verdict.score, 3),
                spent=round(spent, 3),
            )

            if best is None or verdict.score > best[1].score:
                best = (clip, verdict)

            if verdict.score >= self.threshold:
                break  # good enough — stop spending

        assert best is not None
        clip, verdict = best
        return LoopResult(
            clip=clip,
            passed=verdict.score >= self.threshold,
            best_score=round(verdict.score, 3),
            iterations=len(attempts),
            est_cost_usd=round(spent, 3),
            attempts=attempts,
        )

    _last_suggestion: str = ""


def get_quality_loop() -> QualityLoop:
    from backend.services.scene.service import get_scene_service

    return QualityLoop(scenes=get_scene_service(), judge=get_quality_judge())
