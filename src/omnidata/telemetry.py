"""Langfuse tracing (observability): degrade-to-off like every other optional integration in Deps (llm, vector_store,
transcriber, ...). Configure via LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY/LANGFUSE_BASE_URL (config.py); any missing
means tracing is simply off — no network calls, no warnings, call sites unchanged (they get a no-op observation).

Call init(settings) once at process startup (jobs/worker.py::run), before the first observation is started, per
Langfuse's own guidance: import/configure the client before anything that might create a trace.

Only ever pass text through here that has already been through security.pii_masking.mask_pii — traces leave the
process (self-hosted Langfuse, but still an external system), so the same 'no PII in logs' rule (CLAUDE.md #8b)
applies. Callers are responsible for masking before calling in; this module never masks on their behalf."""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .config import Settings

_enabled = False


def init(s: Settings) -> None:
    """Idempotent. Sets the env vars the Langfuse SDK's own get_client() singleton reads, so every later bare
    get_client() call anywhere in the process resolves to the same configured client (SDK's documented pattern)."""
    global _enabled
    if _enabled or not (s.langfuse_public_key and s.langfuse_secret_key and s.langfuse_base_url):
        return
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", s.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", s.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_BASE_URL", s.langfuse_base_url)
    _enabled = True


def enabled() -> bool:
    return _enabled


class _Noop:
    """Returned instead of a real Langfuse observation when tracing is off, so call sites never need an `if`."""

    def update(self, **_: Any) -> _Noop:
        return self


_NOOP = _Noop()


@contextmanager
def observation(as_type: str, name: str, **kwargs: Any) -> Iterator[Any]:
    """One observation (span/generation/tool/...). Nests automatically under whatever observation is currently
    active (OTel context), so callers just need to call this from inside an outer `observation(...)` block."""
    if not _enabled:
        yield _NOOP
        return
    from langfuse import get_client
    with get_client().start_as_current_observation(as_type=as_type, name=name, **kwargs) as obs:  # type: ignore[call-overload]
        yield obs


@contextmanager
def trace_attrs(**kwargs: Any) -> Iterator[None]:
    """Sets trace-level attributes (user_id, session_id, tags, metadata, ...) for every observation created inside
    this block — see Langfuse's propagate_attributes(). No-op when tracing is off."""
    if not _enabled:
        yield
        return
    from langfuse import propagate_attributes
    with propagate_attributes(**kwargs):
        yield
