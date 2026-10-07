"""Private organizer-research concern ordering; never user-facing evidence."""
from __future__ import annotations

CONCERN_PRIORITY_ROWS = (
    {"concern_type": "CHARGING_CONVENIENCE", "priority_rank": 1, "weight": 66},
    {"concern_type": "BATTERY_REPLACEMENT_COST", "priority_rank": 2, "weight": 58},
    {"concern_type": "BATTERY_LIFE", "priority_rank": 3, "weight": 56},
    {"concern_type": "PURCHASE_PRICE", "priority_rank": 4, "weight": 41},
    {"concern_type": "TECH_MATURITY", "priority_rank": 5, "weight": 40},
    {"concern_type": "MAINTENANCE", "priority_rank": 6, "weight": 40},
    {"concern_type": "RANGE", "priority_rank": 7, "weight": 40},
    {"concern_type": "CHARGING_SPEED", "priority_rank": 8, "weight": 34},
    {"concern_type": "WARRANTY", "priority_rank": 9, "weight": 20},
    {"concern_type": "RESALE", "priority_rank": 10, "weight": 9},
    {"concern_type": "SAFETY", "priority_rank": 11, "weight": 1},
)

VISIBILITY = "INTERNAL_ORGANIZER"
RESEARCH_SOURCE_ID = "organizer_toyota_brand_survey_2025_w3"
SNAPSHOT_PERIOD = "2025_W3"

# Labels deliberately omit internal weights and imply no user preference.
EXPLORATION_OPTIONS = (
    ("充電方便嗎", "我比較在意充電方不方便"),
    ("電池壽命", "我比較在意電池壽命"),
    ("換電池費用", "我想了解換電池費用"),
    ("續航", "我比較在意續航"),
    ("車價／成本", "我比較在意車價和使用成本"),
    ("保養／保固", "我比較在意保養和保固"),
)


def concern_priority_rank(concern_type: str) -> int:
    return next((row["priority_rank"] for row in CONCERN_PRIORITY_ROWS if row["concern_type"] == concern_type), 999)
