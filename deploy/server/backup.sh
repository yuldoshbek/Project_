#!/bin/sh
# Ночная копия на сервере агентства: база и файлы презентаций, проверка, неделя хранения
# и копия за пределами сервера (ТЗ, нефункциональные требования: «ночная копия хранится
# отдельно»). Копия, лежащая только на том же диске, умирает вместе с ним.
#
# Запуск — из cron хоста (docs/RUNBOOK.md, «Переезд на сервер агентства»). Копия вне сервера —
# если задан ORBITA_BACKUP_REMOTE (адрес rclone, например `agency-backup:orbita`); без него
# скрипт напоминает об этом в журнале при каждом запуске.
set -eu

cd "$(dirname "$0")"
day="$(date +%F)"
keep_days=7
mkdir -p backups

# Дамп пишется в .part и получает настоящее имя только после проверки: упавший pg_dump
# иначе оставил бы обрезанный файл, который выглядит как копия.
docker compose exec -T postgres sh -c \
    "pg_dump -U orbita -Fc orbita > /backups/orbita-${day}.dump.part"
# Оглавление читается целиком — значит архив цельный.
docker compose exec -T postgres pg_restore --list "/backups/orbita-${day}.dump.part" > /dev/null
mv "backups/orbita-${day}.dump.part" "backups/orbita-${day}.dump"

# Файлы версий презентаций — без них запись о версии открывается отказом «файла нет».
docker compose exec -T api tar -czf - -C /data uploads > "backups/uploads-${day}.tar.gz.part"
gzip -t "backups/uploads-${day}.tar.gz.part"
mv "backups/uploads-${day}.tar.gz.part" "backups/uploads-${day}.tar.gz"

find backups -name 'orbita-*.dump' -mtime +"${keep_days}" -delete
find backups -name 'uploads-*.tar.gz' -mtime +"${keep_days}" -delete

if [ -n "${ORBITA_BACKUP_REMOTE:-}" ]; then
    rclone copy backups "${ORBITA_BACKUP_REMOTE}" --include 'orbita-*.dump' --include 'uploads-*.tar.gz'
    echo "копия ${day}: на сервере и в ${ORBITA_BACKUP_REMOTE}"
else
    echo "копия ${day}: ТОЛЬКО на диске сервера — задайте ORBITA_BACKUP_REMOTE" >&2
fi
