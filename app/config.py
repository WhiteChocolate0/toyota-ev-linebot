from functools import lru_cache
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded only from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=None, env_file_encoding="utf-8")

    app_env: str = "development"
    log_level: str = "INFO"
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    # CURRENT_SUPABASE_PROJECT_REF is the explicit ref for the selected DB.
    # SUPABASE_PROJECT_REF remains as a compatibility alias.
    current_supabase_project_ref: str = ""
    supabase_project_ref: str = ""
    database_role: str = "development"
    # Optional until a distinct, real Production project has been provisioned.
    production_supabase_project_ref: str = ""
    bot_state_schema: str = "public"
    supabase_service_role_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    allowed_origins: str = "http://localhost:5173"
    # Product policy thresholds, kept outside the LINE UI so they can be
    # calibrated from configuration without rewriting conversational copy.
    ev_home_110v_good_max_daily_km: int = 40
    ev_home_110v_warning_max_daily_km: int = 80


@lru_cache
def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().casefold()
    env_specific_file = Path(f".env.{app_env}")
    legacy_file = Path(".env")
    if env_specific_file.is_file():
        env_file = env_specific_file
    elif app_env == "production":
        # Production credentials must come from the hosting environment or an
        # explicit .env.production file, never fall through to local .env.
        env_file = None
    else:
        env_file = legacy_file if legacy_file.is_file() else None
    return Settings(_env_file=str(env_file) if env_file else None)
