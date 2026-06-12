"""API rate limiting — slowapi keyed by client IP.

Video generation triggers ~30 minutes of CPU work per request; an
unthrottled public endpoint is a denial-of-wallet bug. Limits come from
settings so each environment tunes independently (and tests disable it).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import get_settings


def build_limiter() -> Limiter:
    settings = get_settings()
    return Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit_default],
        enabled=settings.rate_limit_enabled,
    )
