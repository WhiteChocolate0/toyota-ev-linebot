from app.services.internal_insights_service import InternalInsightsService
from app.services.knowledge_retriever import knowledge_retriever
from app.services.message_router import route_text_message


class Sources:
    def search_knowledge_sources(self, **_kwargs):
        return [
            {"id": "raw", "source_type": "INTERNAL_AGGREGATED_CDP", "title": "raw CDP row", "content": "女性年齡 40", "priority": 999},
            {"id": "research", "source_type": "INTERNAL_ORGANIZER_RESEARCH", "title": "brand survey", "content": "charging concern", "priority": 999},
            {"id": "official", "source_type": "official", "title": "官方保固資訊", "content": "官方保固", "priority": 1},
        ]


class Benchmarks:
    def __init__(self, rows):
        self.rows = rows

    def get_internal_vehicle_service_benchmark(self, vehicle_id, cohort):
        return self.rows.get((vehicle_id, cohort))


def test_internal_source_not_exposed_to_user():
    results = knowledge_retriever.retrieve(Sources(), "charging concern", "CHARGING")
    assert [result.source["id"] for result in results] == ["official"]


def test_public_rag_filters_internal():
    results = knowledge_retriever.retrieve(Sources(), "charging", "CHARGING")
    assert all(result.source.get("source_type") == "official" for result in results)


def test_raw_cdp_not_used_in_rag():
    assert all(result.source["id"] != "raw" for result in knowledge_retriever.retrieve(Sources(), "40 女性"))


def test_official_data_has_higher_priority():
    results = knowledge_retriever.retrieve(Sources(), "charging concern", "CHARGING")
    assert results[0].source["id"] == "official"


def test_private_uncertainty_uses_neutral_exploration():
    reply = route_text_message("我不確定要不要買電車", "user")
    assert reply is not None and "你比較在意哪一塊" in reply.text
    assert len(reply.quick_replies) == 6
    assert all("%" not in item["action"]["label"] for item in reply.quick_replies)


def test_group_uncertainty_does_not_apply_personalized_market_nudge():
    reply = route_text_message("我不確定要不要買電車", "group")
    assert reply is None


def test_a_currency_not_rendered_as_ntd():
    row = {"vehicle_id": "v1", "vehicle_age_bucket": "13-24", "sample_size": 40, "median_service_amount_a_currency": 1200}
    insight = InternalInsightsService(Benchmarks({("v1", "13-24"): row})).get_vehicle_service_benchmark("v1", "13-24")
    assert insight["currency_type"] == "ANONYMIZED_A_CURRENCY"
    assert "NT$" not in str(insight)


def test_vehicle_age_cohort_required():
    assert InternalInsightsService().get_vehicle_service_benchmark("v1", "")["status"] == "AGE_COHORT_REQUIRED"
    assert InternalInsightsService().compare_service_frequency("v1", "v2", "")["status"] == "AGE_COHORT_REQUIRED"


def test_small_sample_blocked():
    row = {"vehicle_id": "v1", "vehicle_age_bucket": "13-24", "sample_size": 29, "median_service_visits": 2}
    insight = InternalInsightsService(Benchmarks({("v1", "13-24"): row})).get_vehicle_service_benchmark("v1", "13-24")
    assert insight["status"] == "INSUFFICIENT_SAMPLE"
    assert "median_service_visits" not in insight


def test_demographics_not_used_for_recommendation():
    from app.services.recommendation_engine import VehiclePreferenceProfile, shortlist_candidates
    vehicles = [{"id": "v1", "model_name": "bZ4X", "drivetrain": "BEV", "purchase_price_ntd": 1_500_000}]
    profile = VehiclePreferenceProfile(budget_max=2_000_000, priority_factors={"cost"})
    result = shortlist_candidates(profile, vehicles)
    assert result and result[0].vehicle["id"] == "v1"


def test_battery_concern_routing_and_no_replacement_quote():
    life = route_text_message("我怕電池很快壞", "user")
    cost = route_text_message("換電池是不是很貴", "user")
    assert life and life.concern_code == "BATTERY"
    assert cost and "保固" in cost.text
    assert "NT$" not in cost.text


def test_charging_and_range_concern_routes():
    charging = route_text_message("我怕充電不方便", "user")
    range_reply = route_text_message("我怕續航不夠", "user")
    assert charging and charging.concern_code == "CHARGING"
    assert range_reply and range_reply.concern_code == "RANGE"


def test_ev_fit_prioritizes_weak_charging_conditions():
    from app.services.ev_fit_flow import EvFitManager
    assert "固定充電條件" in EvFitManager._summary("attention", "good", "good")
    blocker, _next_step = EvFitManager._blocker("good", "attention", "good", {"home_charge": "UNAVAILABLE"})
    assert blocker == "固定充電條件"
