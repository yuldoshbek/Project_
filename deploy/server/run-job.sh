#!/bin/sh
# Вызвать задачу по расписанию тем же эндпоинтом, что и GitHub Actions в облаке.
# Три попытки: API могли перезапускать на выкладке, и один отказ не должен значить
# пропущенную сводку. Ответ — в журнал контейнера: «почему не пришла» читается там.
set -eu

job="$1"
curl --fail-with-body --silent --show-error \
    --retry 3 --retry-delay 10 --retry-all-errors --max-time 120 \
    --request POST "http://api:8000/internal/jobs/${job}" \
    --header "X-Orbita-Jobs-Secret: ${ORBITA_JOBS_SECRET}" \
    --header 'Content-Type: application/json' \
    --data '{"source":"server-cron"}'
echo " — ${job} $(date '+%Y-%m-%d %H:%M')"
