"""Cast-compose API end-to-end: auth, ownership, cast-aware render + stitch."""

import subprocess
from io import BytesIO

import pytest_asyncio
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.api.v1.auth as auth_api
import backend.api.v1.characters as characters_api
import backend.api.v1.film as film_api
from backend.main import create_app
from backend.models.db import Base
from backend.services.cast.service import CastService
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
        return f"/tmp/{fid}"


def _png():
    b = BytesIO()
    Image.new("RGB", (256, 256), (100, 120, 140)).save(b, "PNG")
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
    async def complete_json_raw(self, system, user):
        return (
            '{"title":"Two Voices","style":"anime","scenes":['
            '{"shot":"aria waves","camera":"static","dialogue":"hi","seconds":4,"role":"ARIA"},'
            '{"shot":"kai replies","camera":"static","dialogue":"hey","seconds":4,"role":"KAI"}]}'
        )


class _Engine:
    def __init__(self, name, real):
        self.name = name
        self.accepts_real_face = real

    async def generate(self, prompt, seconds=4, size="1280x720"):
        return _clip()


@pytest_asyncio.fixture
async def ctx(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/cast.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    char_svc = CharacterService(session_factory=sf, ingest=CharacterIngestService(_MemStorage()))
    monkeypatch.setattr(auth_api, "_session_factory", lambda: sf)
    monkeypatch.setattr(characters_api, "get_character_service", lambda: char_svc)
    # cast binds against the same character service
    monkeypatch.setattr(film_api, "get_cast_service", lambda: CastService(char_svc))
    import backend.services.character.service as char_svc_mod

    monkeypatch.setattr(char_svc_mod, "get_character_service", lambda: char_svc)
    monkeypatch.setattr(film_api, "get_director_service", lambda: DirectorService(_LLM()))
    scenes = SceneService(
        engines={"sora2": _Engine("sora2", False), "kling": _Engine("kling", True)},
        default_engine="sora2",
    )
    monkeypatch.setattr(film_api, "get_composition_service", lambda: CompositionService(scenes))
    client = TestClient(create_app())
    reg = client.post(
        "/api/v1/auth/register", json={"email": "dir@x.com", "password": "password123"}
    ).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}
    yield client, headers
    await engine.dispose()


def _make_avatar(client, headers, name, style, real):
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


def test_cast_compose_requires_auth(ctx):
    client, _ = ctx
    r = client.post(
        "/api/v1/film/cast-compose",
        json={"script": "hi", "cast": [{"role": "X", "avatar_id": "a"}]},
    )
    assert r.status_code == 401


def test_cast_compose_end_to_end(ctx):
    client, headers = ctx
    aria = _make_avatar(client, headers, "Aria", "anime", False)
    kai = _make_avatar(client, headers, "Kai", "realistic", True)
    r = client.post(
        "/api/v1/film/cast-compose",
        json={
            "script": "ARIA greets the audience, then KAI answers.",
            "cast": [
                {"role": "ARIA", "avatar_id": aria, "voice": "v1"},
                {"role": "KAI", "avatar_id": kai},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene_count"] == 2 and body["clip_id"]
    roles = {s["role"]: s["engine"] for s in body["scenes"]}
    assert roles["KAI"] == "kling"  # real person -> reference engine
    assert roles["ARIA"] == "sora2"  # stylized -> sora2


def test_cast_compose_rejects_unowned_avatar(ctx):
    client, headers = ctx
    r = client.post(
        "/api/v1/film/cast-compose",
        json={"script": "X speaks", "cast": [{"role": "X", "avatar_id": "nonexistent"}]},
        headers=headers,
    )
    assert r.status_code == 404
