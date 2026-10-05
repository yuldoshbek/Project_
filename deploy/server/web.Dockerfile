# Интерфейс ORBITA для сервера агентства: сборка Vite и Caddy, который отдаёт её и
# проксирует /api на контейнер API. Один источник для браузера — как прокси Netlify в облаке
# (ADR-0028): cookie сессии первого лица, CORS не нужен.

FROM node:22-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
# Без проверки типов и бюджета: их прогоняет CI до слияния, сборка образа их не повторяет.
RUN npx vite build

FROM caddy:2-alpine
COPY deploy/server/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/dist /srv
