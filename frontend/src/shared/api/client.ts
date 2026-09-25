/**
 * Обращения к API.
 *
 * Три решения, которые дороже всего менять потом.
 *
 * **Адрес относительный — `/api/...`.** Интерфейс и API живут на одном источнике для
 * браузера: Netlify проксирует `/api` на Vercel (ADR-0028). Абсолютный адрес означал бы
 * чужой источник, CORS и cookie третьего лица — то есть отсутствие сессии на iPhone, где
 * такие cookie блокируются по умолчанию.
 *
 * **Cookie отправляется всегда** (`credentials: 'same-origin'`): вход — это личная ссылка
 * и сессия, а не заголовок с токеном (ADR-0029).
 *
 * **401 — это не ошибка запроса, а состояние приложения.** Сессия закончилась, и надо
 * показать «откройте по своей ссылке», а не «внутренняя ошибка». Поэтому у отказа свой
 * тип: экран решает, что с ним делать.
 */

import i18next from '@/shared/i18n';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly type?: string,
  ) {
    super(detail);
    this.name = 'ApiError';
  }

  /** Сессии нет или она закончилась: нужен переход по личной ссылке. */
  get needsLink(): boolean {
    return this.status === 401;
  }

  /** Роль не позволяет действие: руководитель смотрит, а не вносит (ADR-0011). */
  get readOnly(): boolean {
    return this.status === 403;
  }

  /** Отказ, который повтор запроса не исправит: нет сессии или роль не позволяет. */
  get refusal(): boolean {
    return this.needsLink || this.readOnly;
  }
}

/** Что показать человеку вместо ошибки: пояснение API, иначе текст исключения. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return String(error);
}

type Query = Record<string, string | number | boolean | undefined | null>;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
}

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    params.set(key, String(value));
  }
  const tail = params.toString();
  return tail ? `${path}?${tail}` : path;
}

async function readError(response: Response): Promise<ApiError> {
  // Ошибки API приходят в формате problem+json: там есть detail и стабильный type.
  // Если пришло что-то другое (упал прокси, вернулась страница) — не притворяемся, что
  // разобрали, а говорим по существу: код ответа и есть всё, что известно.
  try {
    const body = (await response.json()) as { detail?: string; type?: string };
    return new ApiError(response.status, body.detail ?? response.statusText, body.type);
  } catch {
    return new ApiError(response.status, i18next.t('common.noDetail', { status: response.status }));
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal } = options;

  const init: RequestInit = {
    method,
    // Ровно `same-origin`, не `include`: прокси делает API своим источником, а `include`
    // понадобился бы только при обращении на чужой домен — то есть при поломке ADR-0028.
    credentials: 'same-origin',
  };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  if (signal) init.signal = signal;

  const response = await fetch(withQuery(path, query), init);

  if (!response.ok) {
    throw await readError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
