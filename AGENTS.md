# Repository Guidelines

## Project Structure & Module Organization

- `app/` contains the FastAPI entry point and LINE Bot services. Keep conversation routing and state in `app/services/`; persistence and environment safeguards live in the repository/config modules.
- `tests/` contains unit tests and conversation regression tests. Shared conversation scenarios and fixtures live in `tests/conversations/` and `tests/fixtures/`.
- `scripts/` holds operational checks and offline data tools. `sql/` and `migrations/` contain database SQL; `supabase/` also has legacy migrations—check the current runbook before using any SQL.
- `artifacts/` stores generated analysis and test reports; `docs/` documents current database contracts and readiness.

## Build, Test, and Development Commands

- `.venv/bin/pip install -r requirements.txt` installs dependencies.
- `.venv/bin/uvicorn app.main:app --reload` starts the local API (configure `.env.development` first).
- `.venv/bin/python -m pytest -q` runs the unit suite.
- `make test-conversations` runs conversation regression tests; `make predeploy` runs the deployment gate.
- Before any DB write, run `.venv/bin/python scripts/check_test_environment.py`. Never bypass a failed environment safety check.

## Coding Style & Naming Conventions

Use Python 3.12, four-space indentation, `snake_case` for modules/functions/variables, and `PascalCase` for classes. Keep services focused and preserve repository boundaries: shared official references are read-only, organizer data stays backend-only, and campaign access uses the established handoff contract. Tests use `test_*.py`; conversation cases should describe the intent or regression protected. No formatter/linter is configured; follow nearby code and use clear imports/type hints.

## Testing Guidelines

Add a focused unit test and a conversation scenario for user-visible routing, flow, context, or group-isolation changes. Run the relevant test file, then `make test-conversations` and `make predeploy` for production behavior changes. Keep automated conversation tests on FakeRepository/in-memory fixtures; integration writes must target approved MVP/DEV only.

## Commits & Pull Requests

Git history is unavailable here, so no existing commit convention could be verified. Use concise imperative subjects (for example, `fix: preserve active cost flow`) and keep changes scoped. PRs should describe behavior/risk, list tests, link issues, and include screenshots for UI changes. Call out SQL, environment, or data impact.

## Security & Data Handling

Never commit `.env*`, API keys, or service-role credentials. Current Supabase ref `extkwpghjfttamontqkl` is MVP/DEVELOPMENT, not Production. Do not move Bot state tables or apply legacy SQL without reviewing the current migration runbook. Raw organizer CDP must remain offline; only approved aggregates may be imported, and anonymized A-currency must never be represented as TWD.
