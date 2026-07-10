SHELL := /bin/bash

.PHONY: setup compose-check db-up db-down db-logs migrate dev-api dev-web lint test build check

setup:
	cd backend && uv sync --dev
	cd frontend && corepack enable && pnpm install --frozen-lockfile

compose-check:
	docker compose config --quiet

db-up:
	docker compose up -d --wait db

db-down:
	docker compose down

db-logs:
	docker compose logs -f db

migrate:
	cd backend && uv run alembic upgrade head

dev-api:
	cd backend && uv run python -m tbd

dev-web:
	cd frontend && pnpm dev

lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd frontend && pnpm lint
	cd frontend && pnpm format:check

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

build:
	cd frontend && pnpm build

check: compose-check lint test build
