"""Fail closed if a test run is pointed at a production Supabase project."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from app.services.environment_safety import EnvironmentSafetyError, require_nonproduction_database_write

settings = get_settings()
test_url = os.getenv("TEST_SUPABASE_URL", "")
try:
    environment = require_nonproduction_database_write(settings, operation="integration test")
except EnvironmentSafetyError as exc:
    sys.exit(f"Refusing test writes: {exc}")
if test_url and test_url == settings.supabase_url:
    sys.exit("Refusing test writes: TEST_SUPABASE_URL must not equal SUPABASE_URL.")
if not settings.supabase_service_role_key:
    sys.exit("Refusing DB client check: SUPABASE_SERVICE_ROLE_KEY is missing.")
from supabase import create_client
create_client(settings.supabase_url, settings.supabase_service_role_key)
print(f"PASS: safe {environment.app_env} Supabase client initialized for project {environment.project_ref}.")
