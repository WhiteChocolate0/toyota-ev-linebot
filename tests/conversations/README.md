# Conversation regression contract

`scenarios.py` contains declarative multi-turn conversations. Every `Turn` has:

- `messages`
- `sender_id`
- `source_type`
- `expected_intent`
- `expected_flow`
- `expected_context`
- `must_include`
- `must_not_include`
- `should_reply`
- `should_preserve_flow`

The harness delivers each turn to the real `EventProcessor` with deterministic
catalogue and knowledge-source fixtures. It records rendered reply text rather
than raw Flex JSON, then applies the UX assertions in `ux_assertions.py`.

Run only this deployment gate with:

```sh
make test-conversations
```

Run all deployment checks with:

```sh
make predeploy
```

The latter writes `artifacts/conversation-regression-report.json` and `.md`.
Add a scenario by using `Scenario("short-id", "one of the 15 categories", (...))`;
keep it focused on one conversational promise so a failure identifies a UX
regression rather than a vague routing mismatch.
