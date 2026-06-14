"""FilmSession model accessors + orchestrator (interpret/storyboard/render, edits)."""

import pytest

from backend.models.film_session import FilmSession
from backend.services.film_session.service import FilmSessionService


def test_model_json_accessors_roundtrip():
    fs = FilmSession(id="s1", user_id="u1")
    fs._set("cast_json", [{"role": "ARIA"}])
    fs._set("interpretation_json", {"title": "T"})
    assert fs.cast == [{"role": "ARIA"}]
    assert fs.interpretation == {"title": "T"}
    fs.append_history("user", "hi")
    fs.append_history("assistant", "hello")
    assert len(fs.history) == 2 and fs.history[0]["role"] == "user"


def test_payload_shape():
    fs = FilmSession(id="s1", user_id="u1", title="T", status="done", theme="anime")
    fs.clip_id = "c.mp4"
    fs._set("scenes_json", [{"index": 0}, {"index": 1}])
    p = fs.payload()
    assert p["id"] == "s1" and p["scene_count"] == 2 and p["clip_id"] == "c.mp4"


class _EditLLM:
    def __init__(self, raw):
        self._raw = raw

    async def complete_json_raw(self, system, user):
        return self._raw


@pytest.mark.asyncio
async def test_parse_edit_change_theme():
    svc = FilmSessionService(
        llm=_EditLLM('{"action":"change_theme","scene_index":null,"role":null,"value":"pixar"}')
    )
    fs = FilmSession(id="s", user_id="u")
    fs._set("scenes_json", [{"index": 0}])
    intent = await svc.parse_edit("make it pixar", fs)
    assert intent.action == "change_theme" and intent.value == "pixar"


@pytest.mark.asyncio
async def test_parse_edit_change_voice_with_role():
    svc = FilmSessionService(
        llm=_EditLLM(
            '{"action":"change_voice","scene_index":null,"role":"KAI","value":"deep baritone"}'
        )
    )
    fs = FilmSession(id="s", user_id="u")
    intent = await svc.parse_edit("give Kai a deeper voice", fs)
    assert intent.action == "change_voice" and intent.role == "KAI" and "baritone" in intent.value


@pytest.mark.asyncio
async def test_parse_edit_unknown_is_safe():
    svc = FilmSessionService(llm=_EditLLM("not json"))
    intent = await svc.parse_edit("hmm", FilmSession(id="s", user_id="u"))
    assert intent.action == "unknown"
