.PHONY: up down test lint

up:
	docker compose up --build

down:
	docker compose down

test:
	cd backend && python -m pytest

lint:
	cd backend && ruff check . && black --check .
	cd frontend && npm run lint && npm run build
