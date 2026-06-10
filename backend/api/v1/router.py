"""v1 API router — all route modules register here."""

from fastapi import APIRouter

from backend.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
