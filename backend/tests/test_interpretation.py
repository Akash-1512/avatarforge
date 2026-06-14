"""Interpretation: structured understanding of a film request, with fallback."""

import pytest

from backend.services.interpretation.service import Interpretation, InterpretationService


class _LLM:
    def __init__(self, raw=None, fail=False):
        self._raw = raw
        self._fail = fail

    async def complete_json_raw(self, system, user):
        if self._fail:
            raise RuntimeError("llm down")
        return self._raw


@pytest.mark.asyncio
async def test_interpret_parses_llm_json():
    llm = _LLM(
        '{"title":"Two Voices","premise":"Aria greets, Kai answers.",'
        '"beats":["Aria waves","Kai replies"]}'
    )
    interp = await InterpretationService(llm).interpret(
        "ARIA greets, KAI answers",
        [{"role": "ARIA", "style": "anime", "is_real_person": False}],
        theme="anime",
    )
    assert interp.title == "Two Voices"
    assert "Aria" in interp.premise and len(interp.beats) == 2
    assert interp.cast_summary[0]["role"] == "ARIA"


@pytest.mark.asyncio
async def test_interpret_falls_back_when_llm_fails():
    interp = await InterpretationService(_LLM(fail=True)).interpret(
        "a script", [{"role": "X", "style": "pixar", "is_real_person": False}], theme="pixar"
    )
    assert interp.title == "Untitled Short"
    assert "pixar" in interp.premise and interp.cast_summary[0]["role"] == "X"


def test_human_readable_lists_cast_and_beats():
    i = Interpretation(
        title="T",
        premise="P.",
        beats=["b1", "b2"],
        cast_summary=[{"role": "ARIA", "style": "anime", "is_real_person": False}],
        theme="anime",
    )
    text = i.human_readable()
    assert "**T**" in text and "ARIA" in text and "b1" in text
