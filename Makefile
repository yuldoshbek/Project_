# ORBITA — единые команды разработки.
# На Windows без установленного make: .\make.ps1 <цель> — цели те же.
#
# Канонический список — здесь; при изменении правьте и make.ps1, иначе команды разойдутся.

.DEFAULT_GOAL := help
.PHONY: help install up down reset logs migrate revision heads seed dev dev-back dev-front \
        test test-back test-front e2e check docs fmt reqs job clean

BACKEND  := backend
FRONTEND := frontend

help: ## Показать список целей
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Установить зависимости backend и frontend
	cd $(BACKEND) && uv sync --all-groups
	cd $(FRONTEND) && npm ci

up: ## Поднять PostgreSQL для разработки
	docker compose up -d --wait
	@echo "PostgreSQL :$${ORBITA_DB_PORT:-55432}"

down: ## Остановить окружение (данные сохраняются)
	docker compose down

reset: ## Остановить окружение и удалить данные — база создастся заново
	docker compose down -v

logs: ## Логи окружения
	docker compose logs -f

migrate: ## Применить миграции
	cd $(BACKEND) && uv run alembic upgrade head

revision: ## Создать миграцию по изменившимся моделям: make revision m="описание"
	@test -n "$(m)" || (echo 'укажите описание: make revision m="добавить проекты"'; exit 1)
	cd $(BACKEND) && uv run alembic revision --autogenerate -m "$(m)"
	@echo 'проверьте сгенерированное: автогенерация не видит переименований и данных'

heads: ## Проверить, что голова миграций одна
	cd $(BACKEND) && uv run alembic heads

seed: ## Загрузить справочники; с DEMO=1 — ещё и вымышленные данные
	cd $(BACKEND) && uv run python -m app.seed $(if $(DEMO),--demo,)

dev: ## Запустить backend и frontend
	@echo "Backend: http://localhost:8000   Frontend: http://localhost:5173"
	@$(MAKE) -j2 dev-back dev-front

dev-back:
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --port 8000

dev-front:
	cd $(FRONTEND) && npm run dev

job: ## Выполнить задачу по расписанию вручную: make job n=morning-summary
	@test -n "$(n)" || (echo 'укажите задачу: make job n=morning-summary'; exit 1)
	cd $(BACKEND) && uv run python -m app.jobs.run $(n)

test: test-back test-front ## Прогнать все тесты

test-back:
	cd $(BACKEND) && uv run pytest

test-front:
	cd $(FRONTEND) && npm run test

e2e: ## Playwright на локальной сборке: сценарии и снимки экранов
	cd $(FRONTEND) && npx playwright test

check: ## Линтеры и типы: ruff, mypy, import-linter, eslint, stylelint, tsc, prettier
	cd $(BACKEND) && uv run ruff check .
	cd $(BACKEND) && uv run ruff format --check .
	cd $(BACKEND) && uv run mypy app tests
	cd $(BACKEND) && uv run lint-imports
	cd $(FRONTEND) && npm run lint
	cd $(FRONTEND) && npm run lint:css
	cd $(FRONTEND) && npm run typecheck
	cd $(FRONTEND) && npm run fmt:check
	$(MAKE) docs

docs: ## Проверить документы: ключевые файлы на месте, ссылки целы
	python scripts/check_docs.py

fmt: ## Отформатировать код
	cd $(BACKEND) && uv run ruff format .
	cd $(BACKEND) && uv run ruff check --fix .
	cd $(FRONTEND) && npm run fmt

# Список зависимостей для функций Vercel: платформа ставит их из requirements.txt, а
# единственный источник правды — uv.lock. Забыли пересобрать — в облаке окажется не то,
# что проверено в CI, поэтому CI сверяет файл с блокировкой.
reqs: ## Пересобрать backend/requirements.txt из uv.lock
	cd $(BACKEND) && uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt

clean: ## Удалить кеши и артефакты сборки
	cd $(BACKEND) && rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	cd $(FRONTEND) && rm -rf dist coverage playwright-report test-results
