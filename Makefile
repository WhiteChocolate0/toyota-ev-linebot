.PHONY: test-conversations predeploy

test-conversations:
	.venv/bin/python -m pytest -q tests/conversations

predeploy:
	./scripts/predeploy.sh
