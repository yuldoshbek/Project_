#!/usr/bin/env bash
# Ветки базы Neon: превью каждого PR и ночные снимки рабочей базы.
#
# Почему отдельный скрипт, а не готовое действие из Marketplace: здесь видно, что
# происходит с настоящими данными, и то же самое можно выполнить руками с ноутбука, когда
# конвейер недоступен. Ветка Neon — копия по записи: создаётся секунды и не дублирует
# данные, поэтому снимок дёшев, а превью изолировано.
#
# Правило, которое этот скрипт обслуживает: превью ветвится от демо, а не от рабочей базы
# (CLAUDE.md, инвариант 11). Ветвление от рабочей возможно только для снимка, и такая
# ветка никуда не подключается.
#
# Окружение: NEON_API_KEY, NEON_PROJECT_ID; NEON_DATABASE (по умолчанию orbita),
# NEON_ROLE (по умолчанию orbita).
#
#   scripts/neon.sh branch-id     <имя>
#   scripts/neon.sh branch-create <имя> <родитель>
#   scripts/neon.sh branch-uri    <имя>
#   scripts/neon.sh branch-delete <имя>
#   scripts/neon.sh snapshot      <префикс> <родитель>
#   scripts/neon.sh prune         <префикс> <дней>

set -euo pipefail

: "${NEON_API_KEY:?нужен NEON_API_KEY}"
: "${NEON_PROJECT_ID:?нужен NEON_PROJECT_ID}"
NEON_DATABASE="${NEON_DATABASE:-orbita}"
NEON_ROLE="${NEON_ROLE:-orbita}"

API="https://console.neon.tech/api/v2/projects/${NEON_PROJECT_ID}"

api() {
  local method="$1" path="$2"
  shift 2
  curl --silent --show-error --fail-with-body \
    --request "$method" "${API}${path}" \
    --header "Authorization: Bearer ${NEON_API_KEY}" \
    --header 'Content-Type: application/json' \
    "$@"
}

branches_json() { api GET /branches; }

branch_id() {
  branches_json | jq -r --arg n "$1" '.branches[] | select(.name == $n) | .id' | head -1
}

require_branch_id() {
  local id
  id="$(branch_id "$1")"
  if [ -z "$id" ]; then
    echo "ветки «$1» в проекте нет" >&2
    exit 1
  fi
  echo "$id"
}

# Ждём готовности: создание ветки и точки подключения — асинхронные операции, и запрос
# строки подключения сразу после создания возвращает отказ.
wait_ready() {
  local id="$1" tries=40
  while [ "$tries" -gt 0 ]; do
    if [ "$(api GET "/operations?branch_id=${id}" | jq -r '[.operations[] | select(.status != "finished" and .status != "skipped")] | length')" = "0" ]; then
      return 0
    fi
    sleep 3
    tries=$((tries - 1))
  done
  echo "ветка ${id} не пришла в готовность за две минуты" >&2
  exit 1
}

cmd_branch_create() {
  local name="$1" parent="$2" parent_id existing
  existing="$(branch_id "$name")"
  if [ -n "$existing" ]; then
    # Повторный запуск не создаёт вторую ветку: конвейер запускается на каждый push в PR.
    wait_ready "$existing"
    echo "$existing"
    return 0
  fi
  parent_id="$(require_branch_id "$parent")"
  local id
  id="$(api POST /branches --data "$(jq -n --arg n "$name" --arg p "$parent_id" \
    '{branch: {name: $n, parent_id: $p}, endpoints: [{type: "read_write"}]}')" | jq -r '.branch.id')"
  wait_ready "$id"
  echo "$id"
}

cmd_branch_uri() {
  local id
  id="$(require_branch_id "$1")"
  api GET "/connection_uri?branch_id=${id}&database_name=${NEON_DATABASE}&role_name=${NEON_ROLE}&pooled=true" \
    | jq -r '.uri'
}

cmd_branch_delete() {
  local id
  id="$(branch_id "$1")"
  if [ -z "$id" ]; then
    echo "ветки «$1» нет — удалять нечего"
    return 0
  fi
  api DELETE "/branches/${id}" >/dev/null
  echo "ветка «$1» удалена"
}

# Снимок: ветка от рабочей базы с датой в имени. Точка подключения не создаётся — снимок
# нужен для восстановления, а не для работы, и подключаться к нему некому.
cmd_snapshot() {
  local prefix="$1" parent="$2" name parent_id
  name="${prefix}-$(date --utc +%Y-%m-%d)"
  if [ -n "$(branch_id "$name")" ]; then
    echo "снимок «$name» уже есть — повторный запуск ничего не делает"
    return 0
  fi
  parent_id="$(require_branch_id "$parent")"
  api POST /branches --data "$(jq -n --arg n "$name" --arg p "$parent_id" \
    '{branch: {name: $n, parent_id: $p}}')" >/dev/null
  echo "снимок «$name» создан"
}

# Уборка старых снимков: ветки живут за счёт изменений относительно родителя, и
# накопленные снимки со временем перестают быть бесплатными.
cmd_prune() {
  local prefix="$1" days="$2" cutoff
  cutoff="$(date --utc --date="${days} days ago" +%Y-%m-%d)"
  branches_json | jq -r --arg p "$prefix" '.branches[] | select(.name | startswith($p + "-")) | .name' \
  | while read -r name; do
      local_date="${name#"${prefix}-"}"
      if [[ "$local_date" < "$cutoff" ]]; then
        cmd_branch_delete "$name"
      fi
    done
}

case "${1:-}" in
  branch-id)     branch_id "${2:?нужно имя ветки}" ;;
  branch-create) cmd_branch_create "${2:?нужно имя ветки}" "${3:?нужен родитель}" ;;
  branch-uri)    cmd_branch_uri "${2:?нужно имя ветки}" ;;
  branch-delete) cmd_branch_delete "${2:?нужно имя ветки}" ;;
  snapshot)      cmd_snapshot "${2:?нужен префикс}" "${3:?нужен родитель}" ;;
  prune)         cmd_prune "${2:?нужен префикс}" "${3:?нужно число дней}" ;;
  *)
    sed -n '1,25p' "$0" >&2
    exit 1
    ;;
esac
