"""Optional non-production Supabase integration mode."""

from __future__ import annotations

import os


def test_supabase_configured() -> bool:
    """Only TEST_ credentials opt a caller into DB integration; never production env."""
    return bool(os.getenv("TEST_SUPABASE_URL") and os.getenv("TEST_SUPABASE_KEY"))
