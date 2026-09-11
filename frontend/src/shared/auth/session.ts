/**
 * Сессия пользователя в браузере.
 *
 * **Где что хранится и почему.** Токен доступа живёт только в памяти: он действует
 * пятнадцать минут, и класть его в хранилище значит оставлять его там на месяцы после
 * закрытия вкладки. Токен обновления приходится хранить между перезагрузками, иначе вход
 * требуется после каждого F5 — и человек, которому система нужна раз в день, перестанет
 * ею пользоваться.
 *
 * **Цена этого решения названа вслух.** `localStorage` доступен любому скрипту на
 * странице: межсайтовый сценарий, если он появится, уносит токен обновления. Надёжнее
 * была бы кука `httpOnly`, но её выставляет сервер, а он отдаёт токены телом ответа
 * (ORB-006). Менять это — отдельное решение, а не побочный эффект экрана входа; здесь
 * ограничение зафиксировано, чтобы его не приняли за недосмотр.
 */

const REFRESH_TOKEN_KEY = 'orbita.refresh';

let accessToken: string | null = null;

export interface Tokens {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  must_change_password: boolean;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(value: string | null): void {
  accessToken = value;
}

export function getRefreshToken(): string | null {
  return safeRead();
}

export function rememberTokens(tokens: Tokens): void {
  accessToken = tokens.access_token;
  safeWrite(tokens.refresh_token);
}

export function forgetTokens(): void {
  accessToken = null;
  safeWrite(null);
}

/**
 * Хранилище может быть недоступно: приватное окно, запрет на сайт, политика браузера.
 *
 * Отсутствие хранилища — не повод не работать: пользователь просто будет входить заново
 * после каждой перезагрузки. Падение на этом месте выглядело бы как поломка входа.
 */
function safeRead(): string | null {
  try {
    return globalThis.localStorage?.getItem(REFRESH_TOKEN_KEY) ?? null;
  } catch {
    return null;
  }
}

function safeWrite(value: string | null): void {
  try {
    if (value === null) globalThis.localStorage?.removeItem(REFRESH_TOKEN_KEY);
    else globalThis.localStorage?.setItem(REFRESH_TOKEN_KEY, value);
  } catch {
    /* хранилище недоступно — работаем без него */
  }
}
