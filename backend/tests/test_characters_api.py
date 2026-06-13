"""Character service + API: create from ingest, list, delete, per-user isolation."""

from io import BytesIO

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.api.v1.characters as characters_api
from backend.main import create_app
from backend.models.db import Base
from backend.services.character.ingest import CharacterIngestService
from backend.services.character.service import CharacterService


class _MemStorage:
    def __init__(self):
        self.saved = {}

    async def save_bytes(self, data, extension):
        from backend.services.storage.base import StoredFile

        fid = f"f{len(self.saved)}.{extension}"
        self.saved[fid] = data
        return StoredFile(file_id=fid, path=f"/tmp/{fid}", url=f"/m/{fid}", size_bytes=len(data))

    def resolve_path(self, file_id):
        return f"/tmp/{file_id}"


def _png():
    buf = BytesIO()
    Image.new("RGB", (512, 512), (90, 120, 90)).save(buf, format="PNG")
    return buf.getvalue()


@pytest_asyncio.fixture
async def svc(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/c.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    yield CharacterService(session_factory=sf, ingest=CharacterIngestService(_MemStorage()))
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_photo_character(svc):
    c = await svc.create("u1", "Aria", _png(), source_kind="photo", default_style="anime")
    assert c.frame_count == 1 and c.default_style == "anime"
    got = await svc.get(c.id)
    assert got is not None and got.name == "Aria"
    assert got.frame_ids() == c.frame_ids()


@pytest.mark.asyncio
async def test_unknown_style_rejected(svc):
    from backend.services.character.ingest import IngestError

    with pytest.raises(IngestError):
        await svc.create("u1", "X", _png(), default_style="hologram")


@pytest.mark.asyncio
async def test_list_and_delete_are_per_user(svc):
    a = await svc.create("u1", "A", _png())
    await svc.create("u2", "B", _png())
    assert len(await svc.list_for_user("u1")) == 1
    assert await svc.delete("u2", a.id) is False  # wrong owner
    assert await svc.delete("u1", a.id) is True
    assert await svc.list_for_user("u1") == []


@pytest_asyncio.fixture
async def api(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/api.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    svc = CharacterService(session_factory=sf, ingest=CharacterIngestService(_MemStorage()))
    monkeypatch.setattr(characters_api, "get_character_service", lambda: svc)
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_character_endpoint(api):
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/characters",
        data={
            "user_id": "u1",
            "name": "Nova",
            "source_kind": "photo",
            "default_style": "pixar",
            "is_real_person": "true",
        },
        files={"source": ("face.png", _png(), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["default_style"] == "pixar" and body["frame_count"] == 1
    listed = client.get("/api/v1/characters/u1").json()
    assert len(listed["characters"]) == 1


@pytest.mark.asyncio
async def test_scene_engines_endpoint_lists_routing():
    client = TestClient(create_app())
    info = client.get("/api/v1/scene/engines").json()
    assert "engines" in info and "real_face_capable" in info
