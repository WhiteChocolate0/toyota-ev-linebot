from app.services.vehicle_need_router import VehicleNeedRouter


def test_large_trunk_request_is_a_recommendation_not_unknown() -> None:
    route = VehicleNeedRouter().route("u", "我想要後車廂大一點的")
    assert route is not None
    assert route.classification.topic == "TRUNK_SPACE"
    assert route.classification.user_goal == "RECOMMEND"
    assert route.classification.slots["cargo_space"] == "large"
    assert "一起拆解" not in route.text


def test_trunk_size_is_a_spec_lookup() -> None:
    route = VehicleNeedRouter().route("u", "後車廂大小")
    assert route is not None
    assert route.classification.topic == "TRUNK_SPACE"
    assert route.classification.user_goal == "SPEC_LOOKUP"


def test_ev_trunk_size_captures_powertrain() -> None:
    route = VehicleNeedRouter().route("u", "電動車的後車廂大小")
    assert route is not None
    assert route.classification.topic == "TRUNK_SPACE"
    assert route.classification.slots["powertrain"] == "BEV"
    assert route.classification.user_goal in {"COMPARE", "SPEC_LOOKUP"}


def test_short_recommendation_inherits_trunk_context() -> None:
    router = VehicleNeedRouter()
    router.route("u", "我想要後車廂大一點")
    route = router.route("u", "我想知道建議")
    assert route is not None
    assert route.classification.topic == "TRUNK_SPACE"
    assert route.classification.user_goal == "RECOMMEND"
    assert route.classification.slots["cargo_space"] == "large"


def test_family_space_extracts_family_need() -> None:
    route = VehicleNeedRouter().route("u", "家裡五個人，想要空間大一點")
    assert route is not None
    assert route.classification.topic == "PASSENGER_SPACE"
    assert route.classification.slots["family_use"] is True
    assert route.classification.user_goal == "RECOMMEND"


def test_stroller_is_a_cargo_requirement() -> None:
    route = VehicleNeedRouter().route("u", "會載嬰兒車")
    assert route is not None
    assert route.classification.topic == "TRUNK_SPACE"
    assert route.classification.slots["cargo_requirement"] == "stroller"


def test_camping_is_a_luggage_scenario() -> None:
    route = VehicleNeedRouter().route("u", "常常露營")
    assert route is not None
    assert route.classification.topic == "LUGGAGE_REQUIREMENT"
    assert route.classification.slots["usage_scenario"] == "camping"
