"""Deployment-gate conversation regression tests with UX report artifacts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tests.conversations.harness import ConversationHarness
from tests.conversations.scenarios import SCENARIOS, Scenario, Turn
from tests.conversations.ux_assertions import evaluate
from tests.conversations.conversation_assertions import failure_type


REPORT_DIR = Path("artifacts")


def _observed_intent(reply: str, flow: str | None, context: dict) -> str:
    if "NT$" in reply: return "VEHICLE_PRICE"
    if flow and flow.startswith("COST_CALCULATION"): return "COST_CALCULATION"
    if flow == "EV_FIT": return "EV_FIT"
    if "官方來源" in reply: return "FAQ"
    return str(context.get("last_intent") or "NONE")


def _context_failures(turn: Turn, context: dict) -> list[dict]:
    failures = []
    aliases = {"topic": "active_topic"}
    for key, expected in turn.expected_context.items():
        actual = context.get(aliases.get(key, key))
        if actual != expected:
            failures.append({"assertion": "preserves_context", "detail": f"expected context {key}={expected!r}, got {actual!r}"})
    return failures


def run_suite(scenarios: tuple[Scenario, ...] = SCENARIOS) -> dict:
    report: dict = {"passed_scenarios": [], "failed_scenarios": [], "failure_type": {}, "by_category": {}, "unexpected_intent": [], "unexpected_flow": [], "ux_assertion_failures": []}
    for scenario in scenarios:
        harness = ConversationHarness()
        scenario_failures: list[dict] = []
        for index, turn in enumerate(scenario.turns, start=1):
            observed = harness.send(turn)
            reply, flow = str(observed["reply"]), observed["flow_after"]
            actual_intent = _observed_intent(reply, flow, observed["context"])
            if turn.expected_intent != "ANY" and actual_intent != turn.expected_intent:
                failure = {"turn": index, "input": turn.messages, "expected": turn.expected_intent, "actual_intent": actual_intent, "actual_flow": flow, "actual_response": reply, "assertion": "unexpected_intent", "detail": f"expected {turn.expected_intent}, got {actual_intent}"}
                scenario_failures.append(failure); report["unexpected_intent"].append({"scenario": scenario.id, **failure})
            if turn.expected_flow != "ANY" and (not flow or not flow.startswith(turn.expected_flow)):
                failure = {"turn": index, "input": turn.messages, "expected": turn.expected_flow, "actual_intent": actual_intent, "actual_flow": flow, "actual_response": reply, "assertion": "unexpected_flow", "detail": f"expected {turn.expected_flow}, got {flow}"}
                scenario_failures.append(failure); report["unexpected_flow"].append({"scenario": scenario.id, **failure})
            for failure in evaluate(reply=reply, previous_replies=observed["previous_replies"], must_include=list(turn.must_include), must_not_include=list(turn.must_not_include), should_reply=turn.should_reply, should_preserve_flow=turn.should_preserve_flow, flow_before=observed["flow_before"], flow_after=flow):
                item = {"turn": index, "input": turn.messages, "expected": {"must_include": list(turn.must_include), "should_reply": turn.should_reply}, "actual_intent": actual_intent, "actual_flow": flow, "actual_response": reply, "assertion": failure.assertion, "detail": failure.detail}
                scenario_failures.append(item); report["ux_assertion_failures"].append({"scenario": scenario.id, **item})
            scenario_failures.extend({"turn": index, "input": turn.messages, "actual_intent": actual_intent, "actual_flow": flow, "actual_response": reply, **item} for item in _context_failures(turn, observed["context"]))
        if scenario_failures:
            report["failed_scenarios"].append({"id": scenario.id, "category": scenario.category, "failures": scenario_failures})
        else:
            report["passed_scenarios"].append({"id": scenario.id, "category": scenario.category})
    counts = Counter(failure_type(f["assertion"]) for item in report["failed_scenarios"] for f in item["failures"])
    report["failure_type"] = dict(sorted(counts.items()))
    report["assertion_counts"] = dict(sorted(Counter(f["assertion"] for item in report["failed_scenarios"] for f in item["failures"]).items()))
    categories = Counter(item["category"] for item in report["passed_scenarios"] + report["failed_scenarios"])
    report["by_category"] = dict(sorted(categories.items()))
    report["summary"] = {"total": len(scenarios), "passed": len(report["passed_scenarios"]), "failed": len(report["failed_scenarios"])}
    return report


def write_report(report: dict) -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "conversation-regression-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Conversation regression report", "", f"Total cases: {report['summary']['total']}", f"Passed scenarios: {report['summary']['passed']}", f"Failed scenarios: {report['summary']['failed']}", "", "## By category", ""]
    lines.extend(f"- {name}: {count}" for name, count in report["by_category"].items())
    lines.extend(["", "## Failure type", ""])
    lines.extend(f"- {name}: {count}" for name, count in report["failure_type"].items())
    lines.extend(["", "## Failed scenarios", ""])
    lines.extend(["| Test ID | Step | Input | Expected | Actual Intent | Actual Flow | Failure Type |", "| --- | ---: | --- | --- | --- | --- | --- |"])
    for item in report["failed_scenarios"]:
        for failure in item["failures"]:
            expected = str(failure.get("expected", failure["detail"])).replace("|", "/")
            lines.append(f"| {item['id']} | {failure['turn']} | {failure.get('input', '')} | {expected[:100]} | {failure.get('actual_intent', '')} | {failure.get('actual_flow', '')} | {failure_type(failure['assertion'])} |")
    lines.extend(["", "## Passed scenarios", ""])
    lines.extend(f"- {item['id']} ({item['category']})" for item in report["passed_scenarios"])
    lines.extend(["", "## Unexpected intent", ""])
    lines.extend(f"- {item['scenario']}: {item['detail']}" for item in report["unexpected_intent"])
    lines.extend(["", "## Unexpected flow", ""])
    lines.extend(f"- {item['scenario']}: {item['detail']}" for item in report["unexpected_flow"])
    lines.extend(["", "## UX assertion failures", ""])
    lines.extend(f"- {item['scenario']}: {item['assertion']} — {item['detail']}" for item in report["ux_assertion_failures"])
    (REPORT_DIR / "conversation-regression-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def assert_conversation_regression_suite() -> None:
    report = run_suite()
    write_report(report)
    assert not report["failed_scenarios"], (
        f"{report['summary']['failed']} conversation scenarios failed; "
        "see artifacts/conversation-regression-report.md"
    )
