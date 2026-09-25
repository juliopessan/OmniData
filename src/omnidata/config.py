"""Settings from environment only. Secrets never enter the repo or logs."""
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_timezone: str = "America/Sao_Paulo"
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    database_url_direct: str = ""
    hubspot_access_token: str = ""
    hubspot_portal_id: str = ""
    hubspot_rps: float = Field(default=8, gt=0)
    hubspot_search_rps: float = Field(default=4, gt=0)
    stage_age_default_days: int = 14
    min_n_ranking: int = 20
    model_min_closed: int = 300
    evolution_api_url: str = ""        # e.g. https://evolution.example.com
    evolution_api_key: str = ""        # the server's global AUTHENTICATION_API_KEY
    evolution_instance: str = ""       # instance name to send/receive on (create with `omnidata evolution create-instance`)
    evolution_webhook_secret: str = "" # shared secret we set on Evolution's webhook config; no native signature to check instead
    llm_provider: str = "anthropic"  # anthropic | openai | deepseek
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_router: str = ""
    openai_model_narrator: str = ""
    deepseek_api_key: str = ""  # chat only (OpenAI-compatible API); voice-note transcription stays on OPENAI_API_KEY
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_router: str = ""
    deepseek_model_narrator: str = ""
    openrouter_api_key: str = ""       # fallback provider: tried after the primary (LLM_PROVIDER) if that call errors
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model_router: str = ""  # e.g. "deepseek/deepseek-chat" — OpenRouter's own model catalogue
    openrouter_model_narrator: str = ""
    openrouter_site_url: str = ""      # optional, sent as HTTP-Referer (OpenRouter uses it for their own rate-limit dashboards)
    openrouter_app_name: str = ""      # optional, sent as X-Title
    transcribe_model: str = "gpt-transcribe"
    transcribe_fallback_model: str = "gpt-4o-mini-transcribe"
    transcribe_max_seconds: int = 180
    transcribe_daily_budget_usd: float = 0.10  # per user per day (~22 min of gpt-transcribe)
    anthropic_api_key: str = ""
    alert_daily_cap: int = 5
    alert_quiet_start: str = "20:00"
    alert_quiet_end: str = "07:00"
    rate_limit_msgs_per_hour: int = 60
    user_daily_token_budget: int = 100_000
    ingest_mode: str = "direct"    # direct (own HubSpot client) | airbyte (Airbyte lands tables, we map them)
    airbyte_url: str = ""          # https://api.airbyte.com (Cloud) or your self-managed base URL
    airbyte_client_id: str = ""
    airbyte_client_secret: str = ""
    airbyte_schema: str = "airbyte"
    admin_api_token: str = ""      # protects /api/datasets*; empty = uploads disabled
    cors_origins: str = ""         # comma-separated origins allowed to call the API from a browser
    dataset_max_bytes: int = 10_000_000
    dataset_max_rows: int = 100_000
    webhook_max_bytes: int = 1_000_000  # WhatsApp payloads are small; a bigger body is rejected before the signature is checked
    chroma_url: str = ""               # semantic index only, never the permission boundary (ADR 0009); e.g. http://chroma:8000
    chroma_collection: str = "meeting_transcripts"
    embeddings_model: str = "text-embedding-3-small"  # OpenAI; reuses OPENAI_API_KEY (already set for transcription)
    typing_delay_max_seconds: float = 0.0  # 0 = disabled (tests + default); budget for the "digitando..." pulses (bot/orchestrator.py::_typing_pulses) before replying
    langfuse_public_key: str = ""      # observability (telemetry.py): all three empty = tracing off, same degrade-to-none pattern as every other optional integration
    langfuse_secret_key: str = ""
    langfuse_base_url: str = ""        # self-hosted or regional Langfuse Cloud URL, e.g. https://cloud.langfuse.com
    gmail_user: str = ""                 # single company Gmail account (mailer/gmail.py); empty = "vela" degrades to whatsapp-only
    gmail_from_name: str = "OmniData"
    gmail_client_id: str = ""            # Gmail API + OAuth2 (preferred if set): Google Cloud Console -> OAuth client
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""        # obtained once via scripts/gmail_oauth_setup.py
    gmail_app_password: str = ""         # SMTP fallback (used only if the OAuth vars above are empty): Google Account -> Security -> App passwords
    proposal_company_name: str = "OmniData"  # nome que assina o PDF da proposta (Vela) — a empresa do vendedor, não o produto
    proposal_logo: str = ""                  # caminho de um .svg/.png da SUA marca pro cabeçalho do PDF; vazio = monograma + nome

    @property
    def direct_url(self) -> str:
        return self.database_url_direct or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def hubspot_properties() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / "config" / "hubspot_properties.yaml").read_text())
    return data
