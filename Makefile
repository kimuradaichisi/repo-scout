.PHONY: help install test lint format format-check typecheck check clean

help:
	@echo "Available commands:"
	@echo "  make install       Install dependencies"
	@echo "  make test          Run tests"
	@echo "  make lint          Run Ruff lint"
	@echo "  make format        Format source code"
	@echo "  make format-check  Check formatting"
	@echo "  make typecheck     Run mypy"
	@echo "  make check         Run all quality gates"
	@echo "  make clean         Remove generated files"

install:
	uv sync --extra dev

test:
	uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy src

check: test lint format-check typecheck
	@echo "All quality gates passed."

clean:
	rm -rf \
		.pytest_cache \
		.mypy_cache \
		.ruff_cache \
		.reposcout \
		dist \
		build
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

experiment:
	uv run python tests/experiments/run_ornith_investigation.py

experiment-deterministic:
	uv run python tests/experiments/run_deterministic_investigation.py

experiment-comparison:
	uv run python tests/experiments/run_comparison.py --repeat $(or $(REPEAT),1)