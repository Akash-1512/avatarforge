"""Request-scoped trace context.

A single ContextVar holds the job_id for the pipeline run currently executing
in this task. Set once at pipeline entry, it propagates through every `await`
in the coroutine tree — so the LLM, TTS, and avatar usage recorders can stamp
their audit rows with the originating job without threading job_id through
every service signature. This is the correlation-ID pattern that lets a single
job be reconstructed as an end-to-end trace across the audit tables.
"""

from contextvars import ContextVar
from typing import Optional

_current_job_id: ContextVar[Optional[str]] = ContextVar("current_job_id", default=None)


def set_job_id(job_id: Optional[str]) -> None:
    _current_job_id.set(job_id)


def get_job_id() -> Optional[str]:
    return _current_job_id.get()
