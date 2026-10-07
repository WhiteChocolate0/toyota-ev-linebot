from app.services.powertrain import HEV, normalize_powertrain


def test_legacy_database_powertrain_values_normalize_to_canonical_codes() -> None:
    assert normalize_powertrain("hybrid") == HEV
    assert normalize_powertrain("HEV") == HEV
