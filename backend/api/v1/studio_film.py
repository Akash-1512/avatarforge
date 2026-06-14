"""Studio film API — the conversational, streaming film studio.

- POST /studio/film               create a session from script + cast + theme
- GET  /studio/film/{id}/stream   SSE: stream production (interpret -> render -> done)
- POST /studio/film/{id}/edit     send a chat edit; SSE stream of the change
- GET  /studio/film/{id}          current session state
- GET  /studio/films              list the user's sessions

The SSE endpoints forward the orchestrator's stage events so a chat UI can render the
AI's thinking live. Persistence is checkpointed after each stage, so a dropped
connection leaves a recoverable session.
"""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from backend.api.v1.auth import get_current_user
from backend.models.film_session import FilmSession
from backend.models.user import User
from backend.services.auth.service import decode_token
from backend.services.film_session.service import get_film_session_service

router = APIRouter()


def _sf():
    from backend.models.db import get_session_factory

    return get_session_factory()


async def _load_owned(session_id: str, user_id: str) -> FilmSession:
    async with _sf()() as s:
        fs = await s.get(FilmSession, session_id)
    if fs is None or fs.user_id != user_id:
        raise HTTPException(status_code=404, detail="Film session not found")
    return fs


async def _persist(fs: FilmSession) -> None:
    async with _sf()() as s:
        await s.merge(fs)
        await s.commit()


class CastMemberModel(BaseModel):
    role: str = Field(..., min_length=1, max_length=60)
    avatar_id: str
    voice: str = ""
    style: str = "realistic"
    is_real_person: bool = False


class CreateFilmRequest(BaseModel):
    script: str = Field(..., min_length=3, max_length=8000)
    cast: list[CastMemberModel] = Field(..., min_length=1)
    theme: str = ""


@router.post("/studio/film", status_code=201)
async def create_film(
    req: CreateFilmRequest, current_user: User = Depends(get_current_user)
) -> dict:
    svc = get_film_session_service()
    fs = FilmSession(
        id=svc.new_id(),
        user_id=current_user.id,
        theme=req.theme,
        script=req.script,
        status="created",
    )
    fs._set("cast_json", [m.model_dump() for m in req.cast])
    fs.append_history("user", req.script)
    async with _sf()() as s:
        s.add(fs)
        await s.commit()
    return {"session_id": fs.id, "status": fs.status}


def _sse(gen: AsyncGenerator[dict, None]):
    async def stream():
        try:
            async for ev in gen:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as exc:  # noqa: BLE001 — never break the SSE frame
            yield f"data: {json.dumps({'stage': 'failed', 'message': str(exc)})}\n\n"
        yield 'data: {"stage": "end"}\n\n'

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _user_from_token(token: str) -> User:
    """SSE can't set Authorization headers from EventSource, so accept a token query."""
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    async with _sf()() as s:
        user = await s.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/studio/film/{session_id}/stream")
async def stream_film(session_id: str, token: str = Query(...)):
    user = await _user_from_token(token)
    fs = await _load_owned(session_id, user.id)
    return _sse(get_film_session_service().produce(fs, persist=_persist))


class EditRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/studio/film/{session_id}/edit")
async def edit_film(session_id: str, token: str = Query(...), message: str = Query(...)):
    user = await _user_from_token(token)
    fs = await _load_owned(session_id, user.id)
    return _sse(get_film_session_service().apply_edit(fs, message, persist=_persist))


@router.get("/studio/film/{session_id}")
async def get_film(session_id: str, current_user: User = Depends(get_current_user)) -> dict:
    fs = await _load_owned(session_id, current_user.id)
    return {**fs.payload(), "history": fs.history}


@router.get("/studio/films")
async def list_films(current_user: User = Depends(get_current_user)) -> dict:
    async with _sf()() as s:
        rows = (
            (
                await s.execute(
                    select(FilmSession)
                    .where(FilmSession.user_id == current_user.id)
                    .order_by(desc(FilmSession.updated_at))
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
    return {"films": [fs.payload() for fs in rows]}
