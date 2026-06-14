"""Studio film API: create -> stream produce -> edit, end to end (engines faked)."""

import json
import subprocess
from io import BytesIO

import pytest_asyncio
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.api.v1.auth as auth_api
import backend.api.v1.characters as ch_api
import backend.api.v1.studio_film as sf_api
import backend.services.character.service as char_svc_mod
import backend.services.film_session.service as fss_mod
from backend.main import create_app
from backend.models.db import Base
from backend.services.character.ingest import CharacterIngestService
from backend.services.character.service import CharacterService
from backend.services.composition.service import CompositionService
from backend.services.director.service import DirectorService
from backend.services.scene.service import SceneService


class _MemStorage:
    def __init__(self):
        self.saved = {}

    async def save_bytes(self, data, extension):
        from backend.services.storage.base import StoredFile

        fid = f"f{len(self.saved)}.{extension}"
        self.saved[fid] = data
        return StoredFile(file_id=fid, path=f"/tmp/{fid}", url=f"/m/{fid}", size_bytes=len(data))

    def resolve_path(self, fid):
        return None


def _png():
    b = BytesIO()
    Image.new("RGB", (256, 256), (90, 110, 130)).save(b, "PNG")
    return b.getvalue()


def _clip():
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as t:
        o = os.path.join(t, "c.mp4")
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=1:size=320x240:rate=10",
                "-pix_fmt",
                "yuv420p",
                o,
            ],
            check=True,
        )
        return open(o, "rb").read()


class _LLM:
    """Director + interpretation + edit-parse share this; returns valid JSON for each."""

    async def complete_json_raw(self, system, user):
        if "edit request" in system:
            return '{"action":"change_theme","scene_index":null,"role":null,"value":"pixar"}'
        if "premise" in system or "interpret" in system.lower():
            return (
                '{"title":"Two Voices","premise":"Aria opens, Kai replies.",'
                '"beats":["Aria waves","Kai answers"]}'
            )
        return (
            '{"title":"Two Voices","style":"anime","scenes":['
            '{"shot":"aria waves","camera":"static","dialogue":"hi","seconds":4,"role":"ARIA"}]}'
        )


class _Engine:
    def __init__(self, name, real):
        self.name = name
        self.accepts_real_face = real

    async def generate(self, prompt, seconds=4, size="1280x720", reference_image=None):
        return _clip()


@pytest_asyncio.fixture
async def ctx(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/sf.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    char_svc = CharacterService(session_factory=sf, ingest=CharacterIngestService(_MemStorage()))
    monkeypatch.setattr(auth_api, "_session_factory", lambda: sf)
    monkeypatch.setattr(sf_api, "_sf", lambda: sf)
    monkeypatch.setattr(ch_api, "get_character_service", lambda: char_svc)
    monkeypatch.setattr(char_svc_mod, "get_character_service", lambda: char_svc)
    # film session uses these services
    scenes = SceneService(engines={"sora2": _Engine("sora2", False)}, default_engine="sora2")
    monkeypatch.setattr(fss_mod, "get_director_service", lambda: DirectorService(_LLM()))
    monkeypatch.setattr(fss_mod, "get_composition_service", lambda: CompositionService(scenes))
    from backend.services.cast.service import CastService

    monkeypatch.setattr(fss_mod, "get_cast_service", lambda: CastService(char_svc))
    import backend.services.interpretation.service as interp_mod

    monkeypatch.setattr(
        interp_mod, "get_interpretation_service", lambda: interp_mod.InterpretationService(_LLM())
    )
    monkeypatch.setattr(
        fss_mod, "get_interpretation_service", lambda: interp_mod.InterpretationService(_LLM())
    )
    # FilmSessionService.parse_edit uses self.llm — inject it
    monkeypatch.setattr(fss_mod.FilmSessionService, "llm", property(lambda self: _LLM()))
    client = TestClient(create_app())
    reg = client.post(
        "/api/v1/auth/register", json={"email": "dir@x.com", "password": "password123"}
    ).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    yield client, headers, token, char_svc, sf
    await engine.dispose()


def _avatar(client, headers, name, style, real):
    return client.post(
        "/api/v1/characters",
        data={
            "name": name,
            "source_kind": "photo",
            "default_style": style,
            "is_real_person": str(real).lower(),
        },
        files={"source": ("f.png", _png(), "image/png")},
        headers=headers,
    ).json()["id"]


def _events(text):
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def test_create_requires_auth(ctx):
    client, *_ = ctx
    r = client.post(
        "/api/v1/studio/film", json={"script": "hi", "cast": [{"role": "X", "avatar_id": "a"}]}
    )
    assert r.status_code == 401


def test_full_produce_then_edit_stream(ctx):
    client, headers, token, _, _ = ctx
    aria = _avatar(client, headers, "Aria", "anime", False)
    # create the session
    create = client.post(
        "/api/v1/studio/film",
        json={
            "script": "ARIA greets the audience.",
            "theme": "anime",
            "cast": [
                {
                    "role": "ARIA",
                    "avatar_id": aria,
                    "voice": "warm",
                    "style": "anime",
                    "is_real_person": False,
                }
            ],
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    sid = create.json()["session_id"]

    # stream production
    with client.stream("GET", f"/api/v1/studio/film/{sid}/stream?token={token}") as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    evs = _events(body)
    stages = [e["stage"] for e in evs]
    assert "interpreting" in stages and "interpreted" in stages
    assert "storyboarding" in stages and "rendering" in stages and "done" in stages
    done = [e for e in evs if e["stage"] == "done"][0]
    assert done["data"]["clip_id"]

    # state persisted
    state = client.get(f"/api/v1/studio/film/{sid}", headers=headers).json()
    assert state["status"] == "done" and state["interpretation"]["title"] == "Two Voices"

    # edit via chat (NL -> change_theme -> re-render)
    with client.stream(
        "POST", f"/api/v1/studio/film/{sid}/edit?token={token}&message=make+it+pixar"
    ) as resp:
        assert resp.status_code == 200
        ebody = "".join(resp.iter_text())
    estages = [e["stage"] for e in _events(ebody)]
    assert "thinking" in estages and "done" in estages
    after = client.get(f"/api/v1/studio/film/{sid}", headers=headers).json()
    assert after["theme"] == "pixar"  # the edit applied


def test_films_list_is_per_user(ctx):
    client, headers, token, _, _ = ctx
    aria = _avatar(client, headers, "Aria", "anime", False)
    client.post(
        "/api/v1/studio/film",
        json={
            "script": "hi there",
            "theme": "anime",
            "cast": [{"role": "ARIA", "avatar_id": aria}],
        },
        headers=headers,
    )
    films = client.get("/api/v1/studio/films", headers=headers).json()["films"]
    assert len(films) == 1
