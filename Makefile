.PHONY: install check test lint format db-up db-down migrate run sync compose-up compose-down

install:
	uv sync

check:
	uv run --env-file .env python manage.py check

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

db-up:
	docker compose up -d db

db-down:
	docker compose stop db

migrate:
	uv run --env-file .env python manage.py migrate

run:
	uv run --env-file .env python manage.py runserver

sync:
	uv run --env-file .env python manage.py sync_tdx

compose-up:
	docker compose up --build

compose-down:
	docker compose down
