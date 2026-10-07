#!/usr/bin/env sh
set -eu
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
"$PYTHON_BIN" scripts/check_test_environment.py
"$PYTHON_BIN" -m pytest -q tests
printf '%s\n' 'Conversation UX report: artifacts/conversation-regression-report.md'
