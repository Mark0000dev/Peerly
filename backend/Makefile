.PHONY: check lint typecheck architecture test test-unit test-integration run run-media-worker run-requests-worker run-changes-worker run-ai-worker
check: lint typecheck architecture test
lint:
	uv run ruff check .
	uv run ruff format --check .
typecheck:
	uv run mypy
architecture:
	uv run lint-imports
test:
	uv run pytest --cov --cov-report=term-missing --cov-report=xml
test-unit:
	uv run pytest tests/unit
test-integration:
	uv run pytest tests/integration
run:
	uv run python -m studymate.server --reload

run-media-worker:
	uv run python -m studymate.media_worker

run-requests-worker:
	uv run python -m studymate.requests_worker

run-changes-worker:
	uv run python -m studymate.changes_worker

run-ai-worker:
	uv run python -m studymate.ai_worker
