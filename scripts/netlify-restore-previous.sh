#!/usr/bin/env bash
# Вернуть интерфейс на предыдущую выложенную версию.
#
# Отдельным скриптом, а не строкой в workflow, по одной причине: откат нужен и с ноутбука,
# когда конвейер недоступен или очередь занята. Тот же вызов, тот же результат.
#
# Окружение: NETLIFY_AUTH_TOKEN, NETLIFY_SITE_ID.
#   bash scripts/netlify-restore-previous.sh

set -euo pipefail

: "${NETLIFY_AUTH_TOKEN:?нужен NETLIFY_AUTH_TOKEN}"
: "${NETLIFY_SITE_ID:?нужен NETLIFY_SITE_ID}"

netlify() { npx --yes netlify-cli@latest "$@"; }

# Первая в списке — текущая рабочая версия, вторая — та, на которую откатываемся.
previous="$(netlify api listSiteDeploys --data "{\"site_id\":\"${NETLIFY_SITE_ID}\"}" \
  | jq -r '[.[] | select(.context == "production" and .state == "ready")] | .[1].id // empty')"

if [ -z "$previous" ]; then
  echo "предыдущей рабочей версии интерфейса нет — откатывать некуда" >&2
  exit 1
fi

netlify api restoreSiteDeploy --data "{\"site_id\":\"${NETLIFY_SITE_ID}\",\"deploy_id\":\"${previous}\"}" > /dev/null
echo "интерфейс возвращён на версию ${previous}"
