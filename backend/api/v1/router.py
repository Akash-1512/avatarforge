"""v1 API router — all route modules register here."""

from fastapi import APIRouter

from backend.api.v1 import avatar, health, media, script, tts, videos

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(script.router, tags=["script"])
api_router.include_router(tts.router, tags=["tts"])
api_router.include_router(media.router, tags=["media"])
api_router.include_router(avatar.router, tags=["avatar"])
api_router.include_router(videos.router, tags=["videos"])
