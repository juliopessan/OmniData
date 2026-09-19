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
