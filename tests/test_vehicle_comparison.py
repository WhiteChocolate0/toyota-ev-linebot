from app.services.vehicle_comparison import comparison_text, vehicle_comparison_manager


def profile(identifier: str, name: str, **extra):
    return {"id": identifier, "model_name": name, "drivetrain": "HEV", **extra}


def test_two_and_three_vehicle_comparison_have_fixed_dimensions_and_no_zero_unknown() -> None:
    session, over = vehicle_comparison_manager.set_profiles("two", [profile("a", "bZ4X", purchase_price_ntd=1_280_000), profile("b", "RAV4")])
    assert not over and len(session.vehicle_ids) == 2
    text = comparison_text(session)
    assert "價格" in text and "官方未提供／目前無資料" in text
    session, over = vehicle_comparison_manager.set_profiles("three", [profile("a", "bZ4X"), profile("b", "RAV4"), profile("c", "COROLLA CROSS")])
    assert not over and len(session.vehicle_ids) == 3


def test_fourth_vehicle_requires_replacement() -> None:
    _, over = vehicle_comparison_manager.set_profiles("limit", [profile("a", "A"), profile("b", "B"), profile("c", "C"), profile("d", "D")])
    assert over
