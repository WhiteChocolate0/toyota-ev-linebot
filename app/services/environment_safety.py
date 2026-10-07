"""Fail-closed Supabase environment isolation."""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from app.config import Settings, get_settings


class EnvironmentSafetyError(RuntimeError):
    """Raised before a process can use a database in an unsafe environment."""


@dataclass(frozen=True)
class DatabaseEnvironment:
    app_env: str
    database_role: str
    project_ref: str
    production_project_ref: str


def project_ref_from_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.split(".", 1)[0] if host.endswith(".supabase.co") else ""


def validate_database_environment(settings: Settings | None = None, *, operation: str = "runtime") -> DatabaseEnvironment:
    """Validate the database target before runtime or any write-capable job.

    MVP databases are classified by explicit DATABASE_ROLE, not by historical
    project ref. A production role requires an explicit production ref, and
    APP_ENV and DATABASE_ROLE must agree. A future production ref, when set,
    cannot be used by a development role.
    """
    settings = settings or get_settings()
    app_env = settings.app_env.strip().casefold()
    if app_env not in {"development", "test", "production"}:
        raise EnvironmentSafetyError(f"Unsupported APP_ENV={settings.app_env!r}; use development, test, or production.")
    database_role = settings.database_role.strip().casefold()
    if database_role not in {"development", "production"}:
        raise EnvironmentSafetyError("DATABASE_ROLE must be development or production.")
    if (app_env == "production") != (database_role == "production"):
        raise EnvironmentSafetyError(f"APP_ENV={app_env} is incompatible with DATABASE_ROLE={database_role}.")
    from_url = project_ref_from_url(settings.supabase_url)
    configured = (settings.current_supabase_project_ref or settings.supabase_project_ref).strip()
    if configured and from_url and configured != from_url:
        raise EnvironmentSafetyError("SUPABASE_PROJECT_REF does not match SUPABASE_URL.")
    missing = [name for name, present in (
        ("SUPABASE_URL", bool(settings.supabase_url)),
        ("CURRENT_SUPABASE_PROJECT_REF", bool(configured)),
    ) if not present]
    if missing:
        raise EnvironmentSafetyError("Missing required database environment variables: " + ", ".join(missing) + ".")
    project_ref = configured or from_url
    production_ref = settings.production_supabase_project_ref.strip()
    if not project_ref:
        raise EnvironmentSafetyError("SUPABASE_URL must be a *.supabase.co URL with a project ref.")
    if not re.fullmatch(r"[a-z0-9]{20}", configured):
        raise EnvironmentSafetyError("CURRENT_SUPABASE_PROJECT_REF must be a real 20-character Supabase project ref; placeholders are not allowed.")
    if production_ref and not re.fullmatch(r"[a-z0-9]{20}", production_ref):
        raise EnvironmentSafetyError("PRODUCTION_SUPABASE_PROJECT_REF must be a valid 20-character project ref when configured.")
    if database_role == "development" and production_ref and project_ref == production_ref:
        raise EnvironmentSafetyError(f"Refusing {operation}: DATABASE_ROLE=development cannot connect to the configured Production project.")
    if database_role == "production" and not production_ref:
        raise EnvironmentSafetyError("DATABASE_ROLE=production requires PRODUCTION_SUPABASE_PROJECT_REF.")
    if database_role == "production" and project_ref != production_ref:
        raise EnvironmentSafetyError("Refusing production process: CURRENT_SUPABASE_PROJECT_REF is not the configured Production project.")
    return DatabaseEnvironment(app_env, database_role, project_ref, production_ref)


def require_nonproduction_database_write(settings: Settings | None = None, *, operation: str) -> DatabaseEnvironment:
    environment = validate_database_environment(settings, operation=operation)
    if environment.app_env == "production":
        raise EnvironmentSafetyError(f"Refusing {operation}: this command is DEV/TEST-only and may not write Production.")
    return environment
