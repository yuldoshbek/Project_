# Расписание задач на сервере агентства — cron вместо GitHub Actions (ADR-0028).
FROM alpine:3.20

RUN apk add --no-cache curl tzdata
ENV TZ=Asia/Tashkent

COPY deploy/server/run-job.sh /usr/local/bin/run-job
COPY deploy/server/crontab /etc/crontabs/root
RUN chmod +x /usr/local/bin/run-job

# -f — на переднем плане, -l 2 — пишет запуски в журнал контейнера.
CMD ["crond", "-f", "-l", "2"]
