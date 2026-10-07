from pathlib import Path


CATALOG = Path(__file__).parents[1] / "supabase" / "013_official_vehicle_catalog_2026q3.sql"
LEGACY_SEED = Path(__file__).parents[1] / "supabase" / "007_corolla_cross_gasoline_profiles.sql"
CLEANUP = Path(__file__).parents[1] / "supabase" / "014_database_cleanup.sql"


def test_catalog_is_reproducible_and_uses_only_official_toyota_sources() -> None:
    sql = CATALOG.read_text(encoding="utf-8")
    assert "timestamptz '2026-09-24 00:00:00+08'" in sql
    assert "https://www.toyota.com.tw/showroom/" in sql
    assert "source_kind = 'official'" in sql
    assert "now()" not in sql.split("insert into vehicle_profiles", 1)[1].split("on conflict", 1)[0]


def test_catalog_has_a_hard_freshness_guard_and_quality_gate() -> None:
    sql = CATALOG.read_text(encoding="utf-8")
    assert "valid_until = timestamptz '2026-12-31 23:59:59+08'" in sql
    assert "create or replace view vehicle_profile_quality_issues" in sql
    assert "missing_phev_efficiency" in sql
    assert "expired_or_unbounded" in sql
    assert "invalid_source_url" in sql
    assert "drop constraint if exists vehicle_profiles_drivetrain_check" in sql
    assert "when 'hybrid' then 'HEV'" in sql
    assert "check (drivetrain in ('ICE_GASOLINE', 'ICE_DIESEL', 'HEV', 'PHEV', 'BEV'))" in sql


def test_vehicle_seed_after_powertrain_canonicalisation_uses_a_canonical_code() -> None:
    sql = LEGACY_SEED.read_text(encoding="utf-8")
    assert "'ICE_GASOLINE'" in sql
    assert "'gasoline'" not in sql


def test_cleanup_removes_only_the_unbounded_legacy_seed_and_restores_governed_cc_rows() -> None:
    sql = CLEANUP.read_text(encoding="utf-8")
    assert "drop table if exists group_summaries" in sql
    assert "drop table if exists tax_rules" in sql
    assert "catalog_version is null" in sql
    assert "valid_until is null" in sql
    assert "source_kind = 'official'" in sql
    assert "2026-09-20 19:54:03.250919+00" in sql
    assert "COROLLA CROSS" in sql
    assert "catalog_version = excluded.catalog_version" in sql
    assert "create or replace view vehicle_profile_quality_issues" in sql
