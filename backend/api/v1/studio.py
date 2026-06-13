"""Studio conversational planner + memory API.

The conversational surface over the planner agent, with a transparent,
user-controlled memory layer:

- POST /studio/chat — one turn: appends to the thread, recalls the user's
  long-term memory, asks the planner for an updated VideoPlan, learns durable
  preferences from it, and returns the plan plus the running history.
- GET  /studio/memory/{user_id} — what we remember + the chosen preferences.
- PUT  /studio/preferences/{user_id} — set chosen preferences / memory switch.
- DELETE /studio/memory/{user_id}/{memory_id} — forget one thing.
- DELETE /studio/memory/{user_id} — forget everything.

Identity: user_id is supplied by the client (no auth yet); real identity slots
in here unchanged.
"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.memory.service import get_memory_service
from backend.services.planner.service import get_planner_service

router = APIRouter()


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=2000)
    thread_id: str | None = None


class PreferencesRequest(BaseModel):
    memory_enabled: bool | None = None
    default_tone: str | None = None
    default_language: str | None = None
    default_duration: int | None = None


def _memory_hint(prefs, memories) -> str:
    """Compose a short natural-language hint from chosen + learned memory.
    Chosen preferences take precedence over learned ones for the same kind."""
    chosen = {
        "tone": prefs.default_tone,
        "language": prefs.default_language,
        "duration": str(prefs.default_duration) if prefs.default_duration else None,
    }
    learned = {m["kind"]: m["value"] for m in memories}
    merged = {k: (chosen.get(k) or learned.get(k)) for k in ("tone", "language", "duration")}
    parts = [f"{k}={v}" for k, v in merged.items() if v]
    return ", ".join(parts)


@router.post("/studio/chat")
async def studio_chat(req: ChatRequest) -> dict:
    mem = get_memory_service()
    planner = get_planner_service()
    thread_id = req.thread_id or uuid.uuid4().hex

    prefs = await mem.get_preferences(req.user_id)
    memories = await mem.recall(req.user_id)
    hint = _memory_hint(prefs, memories)

    history = await mem.load_thread(thread_id)
    await mem.append_message(thread_id, req.user_id, "user", req.message)

    plan = await planner.chat(req.message, history=history, memory_hint=hint)

    assistant_text = (
        f"{plan.rationale} "
        f"[{plan.tone} · {plan.language} · {plan.duration_seconds}s · {plan.engine}]"
    )
    await mem.append_message(thread_id, req.user_id, "assistant", assistant_text)
    await mem.extract_from_plan(req.user_id, plan, req.message)

    return {
        "thread_id": thread_id,
        "plan": plan.model_dump(),
        "assistant_message": assistant_text,
        "history": await mem.load_thread(thread_id),
        "memory_applied": hint,
    }


@router.get("/studio/memory/{user_id}")
async def studio_memory(user_id: str) -> dict:
    view = await get_memory_service().view(user_id)
    return {
        "user_id": user_id,
        "preferences": {
            "memory_enabled": view.preferences.memory_enabled,
            "default_tone": view.preferences.default_tone,
            "default_language": view.preferences.default_language,
            "default_duration": view.preferences.default_duration,
        },
        "memories": view.memories,
    }


@router.put("/studio/preferences/{user_id}")
async def set_preferences(user_id: str, req: PreferencesRequest) -> dict:
    prefs = await get_memory_service().set_preferences(user_id, **req.model_dump())
    return {
        "user_id": user_id,
        "preferences": {
            "memory_enabled": prefs.memory_enabled,
            "default_tone": prefs.default_tone,
            "default_language": prefs.default_language,
            "default_duration": prefs.default_duration,
        },
    }


@router.delete("/studio/memory/{user_id}/{memory_id}")
async def delete_memory(user_id: str, memory_id: int) -> dict:
    ok = await get_memory_service().delete_memory(user_id, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": memory_id}


@router.delete("/studio/memory/{user_id}")
async def clear_memory(user_id: str) -> dict:
    n = await get_memory_service().clear_memories(user_id)
    return {"cleared": n}
