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
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    llm_provider: str = "anthropic"  # anthropic | openai
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_router: str = ""
    openai_model_narrator: str = ""
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
