"""CLI runner for deterministic, offline conversation regression tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tests.test_conversation_regression import run_suite, write_report

from .scenarios import SCENARIOS


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 電車解惑所 conversation regressions")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--case", dest="case_ids", action="append", default=[])
    parser.add_argument("--failed-only", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    selected = tuple(case for case in SCENARIOS if (not args.category or case.category in args.category) and (not args.case_ids or case.id in args.case_ids))
    report = run_suite(selected)
    if args.report:
        write_report(report)
    rows = report["failed_scenarios"] if args.failed_only else report["passed_scenarios"] + report["failed_scenarios"]
    print(json.dumps({"summary": report["summary"], "scenarios": rows}, ensure_ascii=False, indent=2))
    return 1 if report["failed_scenarios"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
