.PHONY: setup check check-backend check-frontend lint test format api ui

setup:
	uv sync --locked --group dev
	npm --prefix frontend ci

check: check-backend check-frontend

check-backend: lint test

check-frontend:
	npm --prefix frontend run check

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked python scripts/check_repository.py

test:
	uv run --locked pytest -q

format:
	uv run --locked ruff format .

api:
	bash scripts/run.sh

ui:
	npm --prefix frontend run dev
