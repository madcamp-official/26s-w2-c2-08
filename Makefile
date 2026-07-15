SHELL := /bin/bash

.PHONY: setup compose-check deploy-check db-up db-down db-logs migrate dev-api dev-web \
	skills-sync skills-check docs-check backend-lint backend-format frontend-lint \
	frontend-format lint frontend-typecheck typecheck backend-unit backend-contract \
	backend-integration migration-check frontend-test test frontend-contract-check \
	frontend-build frontend-visual build check

setup:
	cd backend && uv sync --dev
	cd frontend && corepack enable && pnpm install --frozen-lockfile

compose-check:
	docker compose config --quiet

deploy-check:
	bash -n deploy/bin/goal-deploy deploy/bin/goal-deploy-if-needed
	python3 -m unittest discover -s deploy/tests -p 'test_*.py'

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

skills-sync:
	python3 scripts/sync_skills.py sync

skills-check:
	python3 scripts/sync_skills.py check

docs-check:
	python3 scripts/check_docs.py

backend-lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff check ../scripts/check_docs.py

backend-format:
	cd backend && uv run ruff format --check .
	cd backend && uv run ruff format --check ../scripts/check_docs.py

frontend-lint:
	cd frontend && pnpm lint

frontend-format:
	cd frontend && pnpm format:check

lint: backend-lint backend-format frontend-lint frontend-format

frontend-typecheck:
	cd frontend && pnpm typecheck

typecheck: frontend-typecheck

backend-unit:
	cd backend && uv run pytest -m "unit and not contract"

backend-contract:
	cd backend && uv run pytest -m contract

backend-integration:
	cd backend && uv run pytest -m "integration and not migration"

migration-check:
	cd backend && uv run pytest -m migration

frontend-test:
	cd frontend && pnpm test

test: backend-unit backend-contract backend-integration migration-check frontend-test

frontend-contract-check:
	cd frontend && pnpm api:check

frontend-build:
	cd frontend && pnpm build

frontend-visual:
	cd frontend && pnpm visual:foundation

build: frontend-build

check: skills-check compose-check deploy-check docs-check lint typecheck frontend-contract-check test build
