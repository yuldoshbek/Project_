/**
 * Стенд сценариев на машине разработчика — отдельно от окна разработки.
 *
 * Прогон на базе разработки выбивал разработчика из его же вкладки: каждый файл сценариев
 * выпускает ссылку заново, а перевыпуск закрывает прежние сессии роли (ADR-0029). И
 * расходовал вымышленные данные, так что через десяток прогонов сценарии падали не от кода.
 * Поэтому локально Playwright поднимает свой API на своей базе, которая пересоздаётся перед
 * каждым прогоном (`backend/app/e2e_stand.py`), и свой Vite с прокси на этот API. `make dev`
 * на 8000 и 5173 прогон не трогает.
 *
 * Свой стенд — когда это не конвейер и адрес не задан. В CI окружение задаёт конвейер
 * (свежая база, собранный интерфейс). `ORBITA_E2E_URL` — прогон по уже поднятым серверам:
 * тогда и ссылки выпускаются в базе из `.env`, как раньше.
 */

export const LOCAL_STAND = !process.env.CI && !process.env.ORBITA_E2E_URL;

export const STAND_API_PORT = 8001;
export const STAND_WEB_PORT = 5174;
export const STAND_URL = `http://localhost:${STAND_WEB_PORT}`;

/**
 * База стенда. Пустая строка подключения — чтобы перебить её из `.env`: база собирается из
 * частей `ORBITA_DB_*`, и имя `*_e2e` — единственное, что стенд согласен пересоздать.
 */
export const STAND_DB_ENV = {
  ORBITA_DATABASE_URL: '',
  ORBITA_DB_NAME: process.env.ORBITA_E2E_DB ?? 'orbita_e2e',
} as const;

/** Окружение процесса плюс своё: `undefined` из `process.env` дочерний процесс не примет. */
export function withEnv(extra: Record<string, string>): Record<string, string> {
  const own = Object.entries(process.env).filter(
    (entry): entry is [string, string] => entry[1] !== undefined,
  );
  return { ...Object.fromEntries(own), ...extra };
}
