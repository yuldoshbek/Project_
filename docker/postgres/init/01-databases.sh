#!/bin/bash
# Выполняется один раз, при создании тома postgres-data.
#
# Делает две вещи:
#   1. Создаёт тестовую базу рядом с рабочей — тесты не должны затирать данные разработки.
#   2. Включает расширения в обеих базах. Расширения требуют прав суперпользователя,
#      поэтому их место здесь, при подготовке окружения, а не в миграции приложения.
#      Схему orbita создаёт Alembic (ORB-004) — она принадлежит приложению, а не окружению.
set -euo pipefail

TEST_DB="${ORBITA_TEST_DB:-orbita_test}"

if ! psql --username "$POSTGRES_USER" --dbname postgres -tAc \
	"SELECT 1 FROM pg_database WHERE datname = '${TEST_DB}'" | grep -q 1; then
	createdb --username "$POSTGRES_USER" "$TEST_DB"
	echo "создана тестовая база ${TEST_DB}"
fi

for db in "$POSTGRES_DB" "$TEST_DB"; do
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
		-- поиск с опечатками и частичным вводом (ADR-0006)
		CREATE EXTENSION IF NOT EXISTS pg_trgm;
		-- снятие диакритики при нормализации поискового текста (ADR-0006)
		CREATE EXTENSION IF NOT EXISTS unaccent;
		-- регистронезависимый citext для адресов почты
		CREATE EXTENSION IF NOT EXISTS citext;
		-- gen_random_uuid для первичных ключей
		CREATE EXTENSION IF NOT EXISTS pgcrypto;
	EOSQL
	echo "расширения включены в базе ${db}"
done
