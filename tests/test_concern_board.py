from app.services.concern_board import build_concern_board, concern_type, status_from_signal


def test_battery_concern_is_open_and_board_never_contains_people() -> None:
    assert concern_type("BATTERY") == "BATTERY"
    assert status_from_signal("BATTERY", "concerned") == "OPEN"
    board = build_concern_board([{"concern_type": "BATTERY", "status": "OPEN"}])
    assert "電池" in board and "爸爸" not in board and "媽媽" not in board


def test_board_groups_are_callers_data_not_global_state() -> None:
    first = build_concern_board([{"concern_type": "COST", "status": "CLARIFIED"}])
    second = build_concern_board([{"concern_type": "CHARGING", "status": "NEEDS_VERIFICATION"}])
    assert "使用成本" in first and "家庭充電" not in first
    assert "家庭充電" in second and "使用成本" not in second
