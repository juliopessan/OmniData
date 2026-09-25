"""Worker: message loop + scheduler. Jobs are guarded by Postgres advisory locks (one run at a time)."""
from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .. import telemetry
from ..alerts import engine
from ..bot import actions
from ..bot.evolution import EvolutionGateway
from ..bot.orchestrator import Deps, process_next, requeue_stuck
from ..config import ROOT, Settings, get_settings
from ..crm.hubspot.client import HubSpotClient
from ..crm.hubspot.writeback import HubSpotWriter
from ..db import advisory_lock, connect
from ..ingest import jobs as ingest_jobs
from ..ingest.backup import backup
from ..llm.anthropic import AnthropicClient
from ..llm.base import LlmClient
from ..llm.fallback import FallbackLlmClient
from ..llm.openai_chat import OpenAIChatClient
from ..llm.transcribe import OpenAITranscriber, Transcriber
from ..mailer.gmail import GmailSender
from ..rag.chroma import ChromaStore, VectorStore
from ..rag.embeddings import Embeddings, OpenAIEmbeddings

log = logging.getLogger("omnidata.worker")


def _build_primary(s: Settings) -> LlmClient | None:
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        return AnthropicClient(s.anthropic_api_key)
    if s.llm_provider == "openai" and s.openai_api_key and s.openai_model_router and s.openai_model_narrator:
        return OpenAIChatClient(s.openai_api_key, s.openai_model_router, s.openai_model_narrator, s.openai_base_url)
    if s.llm_provider == "deepseek" and s.deepseek_api_key and s.deepseek_model_router and s.deepseek_model_narrator:
        return OpenAIChatClient(s.deepseek_api_key, s.deepseek_model_router, s.deepseek_model_narrator, s.deepseek_base_url, provider="deepseek")
    return None


def _build_openrouter(s: Settings) -> LlmClient | None:
    if not (s.openrouter_api_key and s.openrouter_model_router and s.openrouter_model_narrator):
        return None
    headers = {k: v for k, v in (("HTTP-Referer", s.openrouter_site_url), ("X-Title", s.openrouter_app_name)) if v}
    return OpenAIChatClient(s.openrouter_api_key, s.openrouter_model_router, s.openrouter_model_narrator,
                            s.openrouter_base_url, provider="openrouter", extra_headers=headers or None)


def build_llm(s: Settings) -> LlmClient | None:
    """Primary from LLM_PROVIDER; OpenRouter, if configured, is tried after it on any provider error (never before).
    With only OPENROUTER_* set (no primary), OpenRouter is used alone. Neither configured: degraded (keyword/menu) mode."""
    primary, fallback = _build_primary(s), _build_openrouter(s)
    if primary and fallback:
        def log_fallback(_from: str, to: str, exc: Exception) -> None:
            log.warning("llm fallback: %s -> %s (%s)", _from, to, exc)
        return FallbackLlmClient([(primary, s.llm_provider), (fallback, "openrouter")], on_fallback=log_fallback)
    return primary or fallback  # degraded (keyword/menu) mode if neither is configured


def build_transcriber(s: Settings) -> Transcriber | None:
    if not s.openai_api_key:
        return None  # audio then gets a polite 'write instead' reply
    return OpenAITranscriber(s.openai_api_key, s.transcribe_model, s.transcribe_fallback_model, s.openai_base_url, s.transcribe_max_seconds)


def build_embeddings(s: Settings) -> Embeddings | None:
    if not s.openai_api_key:
        return None  # Atlas then reports no meetings found, same degraded shape as any other missing dependency
    return OpenAIEmbeddings(s.openai_api_key, s.embeddings_model, s.openai_base_url)


def build_vector_store(s: Settings) -> VectorStore | None:
    if not s.chroma_url:
        return None
    return ChromaStore(s.chroma_url, s.chroma_collection)


def build_emailer(s: Settings) -> GmailSender | None:
    if not (s.gmail_user and s.gmail_app_password):
        return None  # Vela then reports "e-mail indisponível" and (if asked) sends only via WhatsApp
    return GmailSender(s.gmail_user, s.gmail_app_password, s.gmail_from_name)


async def _locked(key: int, fn):  # type: ignore[no-untyped-def]
    try:
        with connect(direct=True) as conn, advisory_lock(conn, key):
            return await fn(conn)
    except RuntimeError as exc:
        log.info("skip job %s: %s", key, exc)
    except Exception as exc:  # a failing job must not kill the worker
        log.error("job %s failed: %s", key, type(exc).__name__)


async def run(s: Settings | None = None) -> None:
    s = s or get_settings()
    telemetry.init(s)  # before anything that might create a trace (LlmClient calls happen inside process_next)
    gw = EvolutionGateway(s.evolution_api_url, s.evolution_api_key, s.evolution_instance)
    hs = HubSpotClient(s.hubspot_access_token, rps=s.hubspot_rps, search_rps=s.hubspot_search_rps) if s.hubspot_access_token else None
    deps = Deps(gateway=gw, writer=HubSpotWriter(hs) if hs else None, llm=build_llm(s), settings=s, transcriber=build_transcriber(s),
                embeddings=build_embeddings(s), vector_store=build_vector_store(s), emailer=build_emailer(s))

    async def ingest_and_alert() -> None:
        async def job(conn):  # type: ignore[no-untyped-def]
            if s.ingest_mode == "airbyte":  # Airbyte lands tables on its own schedule; we only map what is new
                from ..integrations.airbyte.landing import ingest as airbyte_ingest
                airbyte_ingest(conn, s.airbyte_schema)
            elif hs:
                await ingest_jobs.incremental(conn, hs)
            engine.evaluate(conn)
            await engine.dispatch(conn, gw, s)
        await _locked(7002, job)

    async def briefs() -> None:
        await _locked(7003, lambda conn: engine.morning_briefs(conn, gw))

    async def recap() -> None:
        await _locked(7006, lambda conn: engine.evening_recaps(conn, gw))

    async def housekeeping() -> None:
        async def job(conn):  # type: ignore[no-untyped-def]
            actions.expire_pending(conn)
            requeue_stuck(conn)
            with conn.cursor() as cur:
                cur.execute("delete from bronze.hubspot_raw where ingested_at < now() - interval '30 days'")
                cur.execute("delete from app.wa_message where received_at < now() - interval '90 days'")
                cur.execute("delete from app.llm_call where created_at < now() - interval '180 days'")
            conn.commit()
        await _locked(7004, job)

    async def snapshot() -> None:
        async def job(conn):  # type: ignore[no-untyped-def]
            ingest_jobs.weekly_snapshot(conn)
        await _locked(7005, job)

    async def nightly_backup() -> None:
        try:
            await asyncio.to_thread(backup, s.direct_url, Path(ROOT / "backups"))
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            log.error("backup failed: %s", type(exc).__name__)

    sched = AsyncIOScheduler(timezone=s.app_timezone)
    sched.add_job(ingest_and_alert, "interval", minutes=15, next_run_time=datetime.now(UTC), max_instances=1, coalesce=True)
    sched.add_job(briefs, "interval", minutes=5, max_instances=1, coalesce=True)
    sched.add_job(recap, "interval", minutes=5, max_instances=1, coalesce=True)
    sched.add_job(housekeeping, "interval", minutes=5, max_instances=1, coalesce=True)
    sched.add_job(snapshot, "cron", day_of_week="mon", hour=2)
    sched.add_job(nightly_backup, "cron", hour=3)
    sched.start()
    log.info("worker started (llm=%s, hubspot=%s, tracing=%s)", "on" if deps.llm else "degraded",
              "on" if hs else "off", "on" if telemetry.enabled() else "off")

    with connect() as conn:
        while True:
            try:
                if not await process_next(conn, deps):
                    await asyncio.sleep(1)
            except Exception as exc:
                log.error("loop error: %s", type(exc).__name__)
                conn.rollback()
                await asyncio.sleep(2)
