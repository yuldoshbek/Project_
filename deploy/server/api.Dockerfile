# API ORBITA для сервера агентства (ADR-0028): тот же код, что в облаке, под uvicorn.
#
# Зависимости — из backend/requirements.txt, то есть из uv.lock без инструментов разработки
# (`make reqs`): контейнер ставит ровно то, что проверено в CI.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .
COPY deploy/server/api-start.sh /usr/local/bin/api-start
RUN chmod +x /usr/local/bin/api-start \
    && useradd --system --uid 10001 --home /app orbita \
    && mkdir -p /data/uploads \
    && chown -R orbita /app /data

USER orbita
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["api-start"]
