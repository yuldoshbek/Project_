# ORBITA — единые команды разработки.
# На Windows без установленного make используйте .\make.ps1 <цель> — цели те же.
#
# Часть целей опирается на артефакты соседних тикетов и заработает вместе с ними:
#   up, down, logs   — ORB-002 (docker-compose)
#   migrate, seed    — ORB-004 (Alembic) и ORB-007 (сиды)
#   dev              — ORB-003 (приложение FastAPI) и ORB-005 (оболочка frontend)

.DEFAULT_GOAL := help
.PHONY: help install up down reset logs migrate seed dev dev-back dev-front test test-back test-front check fmt clean

BACKEND  := backend
FRONTEND := frontend

help: ## Показать список целей
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Установить зависимости backend и frontend
	cd $(BACKEND) && uv sync --all-groups
	cd $(FRONTEND) && npm ci

up: ## Поднять окружение и дождаться готовности всех сервисов
	docker compose up -d --wait
	docker compose run --rm minio-init
	@echo "PostgreSQL :$${ORBITA_DB_PORT:-55432}   Redis :$${ORBITA_REDIS_PORT:-56379}"
	@echo "MinIO http://localhost:$${ORBITA_S3_CONSOLE_PORT:-59001}   Почта http://localhost:$${ORBITA_MAIL_UI_PORT:-58025}"

down: ## Остановить окружение (данные сохраняются)
	docker compose down

reset: ## Остановить окружение и удалить данные — база создастся заново
	docker compose down -v

logs: ## Логи окружения
	docker compose logs -f

migrate: ## Применить миграции
	cd $(BACKEND) && uv run alembic upgrade head

seed: ## Загрузить справочники и демо-данные
	cd $(BACKEND) && uv run python -m app.seed

dev: ## Запустить backend и frontend
	@echo "Backend: http://localhost:8000   Frontend: http://localhost:5173"
	@$(MAKE) -j2 dev-back dev-front

dev-back:
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --port 8000

dev-front:
	cd $(FRONTEND) && npm run dev

test: test-back test-front ## Прогнать все тесты

test-back:
	cd $(BACKEND) && uv run pytest

test-front:
	cd $(FRONTEND) && npm run test

check: ## Линтеры и типы: ruff, mypy, import-linter, eslint, tsc, prettier
	cd $(BACKEND) && uv run ruff check .
	cd $(BACKEND) && uv run ruff format --check .
	cd $(BACKEND) && uv run mypy app tests
	cd $(BACKEND) && uv run lint-imports
	cd $(FRONTEND) && npm run lint
	cd $(FRONTEND) && npm run typecheck
	cd $(FRONTEND) && npm run fmt:check

fmt: ## Отформатировать код
	cd $(BACKEND) && uv run ruff format .
	cd $(BACKEND) && uv run ruff check --fix .
	cd $(FRONTEND) && npm run fmt

clean: ## Удалить кеши и артефакты сборки
	cd $(BACKEND) && rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	cd $(FRONTEND) && rm -rf dist coverage
