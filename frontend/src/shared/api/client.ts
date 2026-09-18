/**
 * Обращение к API.
 *
 * Один вход для всех запросов: токен подставляется здесь, а не в каждом вызове — иначе
 * однажды его забудут, и запрос уйдёт без него. Код ответа доходит до вызывающего кода
 * в виде поля, а не текста: по нему решается, повторять ли запрос и куда вести
 * пользователя.
 *
 * Различие 401 и 403 — не формальность (см. `app/api/errors.py` на стороне сервера).
 * По 401 пользователя уводят на вход: сессия кончилась. По 403 оставляют на месте и
 * показывают сообщение: он вошёл, но это действие не его. Пока коды были одинаковыми,
 * отказ руководителю в записи был неотличим от истёкшей сессии.
 */

export const API_PREFIX = '/api/v1';

/** Тело ошибки по RFC 9457, как его отдаёт сервер. */
interface ProblemDetails {
  type?: string;
  title?: string;
  detail?: string;
  request_id?: string;
  /** Разбор по полям — только у 422 (`app/api/errors.py`, обработчик проверки запроса). */
  errors?: { field?: string; message?: string }[];
}

export class HttpError extends Error {
  readonly status: number;
  readonly type: string | undefined;
  readonly requestId: string | undefined;

  /**
   * Отказы по полям: имя поля → сообщение сервера.
   *
   * Разбор живёт здесь, а не в каждой форме: форм будет несколько, а форма ответа одна.
   * Ошибка, показанная только сверху общей строкой, заставляет искать поле глазами — и
   * на форме из четырнадцати полей это ищут долго.
   */
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(status: number, problem: ProblemDetails) {
    super(problem.detail ?? problem.title ?? `HTTP ${String(status)}`);
    this.name = 'HttpError';
    this.status = status;
    this.type = problem.type;
    this.requestId = problem.request_id;

    const byField: Record<string, string> = {};
    for (const entry of problem.errors ?? []) {
      // Первое сообщение на поле, а не последнее: у одного поля отказов может быть
      // несколько, и человеку нужен первый, а не тот, что оказался в конце списка.
      if (entry.field !== undefined && entry.message !== undefined && !(entry.field in byField)) {
        byField[entry.field] = entry.message;
      }
    }
    this.fieldErrors = byField;
  }
}

/** Заголовок, которым запрос подписывает действующее лицо (ADR-0026). */
export const ACTOR_HEADER = 'X-Orbita-Actor';

/** Возвращает текущий режим работы: помощник или руководитель. */
export type ActorSource = () => string;

/**
 * Входа в системе нет, и токена тоже. Запрос сообщает лишь, в каком режиме работает
 * человек, — сервер верит этому на слово и подписывает его именем изменения в журнале.
 * Охрана живёт на периметре, а не в этом файле (ADR-0026).
 */
let readActor: ActorSource = () => 'assistant';

export function configureApi(source: ActorSource): void {
  readActor = source;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query } = options;

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  headers[ACTOR_HEADER] = readActor();

  // Ключ `body` не появляется вовсе, когда тела нет: при строгих необязательных
  // свойствах `undefined` и «нет свойства» — разные вещи, и `fetch` принимает второе.
  const init: RequestInit = { method, headers };
  if (body !== undefined) init.body = JSON.stringify(body);

  const response = await fetch(`${API_PREFIX}${path}${buildQuery(query)}`, init);

  if (response.status === 204) return undefined as T;

  if (!response.ok) {
    const problem = await safeProblem(response);
    throw new HttpError(response.status, problem);
  }

  return (await response.json()) as T;
}

/**
 * Загрузка файла на сервер.
 *
 * Тело собирается `FormData`, и заголовок `Content-Type` здесь **не ставится**: браузер
 * дописывает к нему границу частей, без которой сервер не разберёт тело. Поставить его
 * руками — значит получить отказ на каждой загрузке.
 *
 * Файл идёт через приложение, а не прямой подписанной ссылкой в хранилище, и это
 * намеренно: только так его успевают проверить антивирусом и посчитать отпечаток до
 * того, как он где-либо окажется (Q7, ADR-0009). Ссылкой файл только **раздаётся**.
 */
export async function requestUpload<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  headers[ACTOR_HEADER] = readActor();

  const response = await fetch(`${API_PREFIX}${path}`, { method: 'POST', headers, body: form });

  if (!response.ok) {
    const problem = await safeProblem(response);
    throw new HttpError(response.status, problem);
  }

  return (await response.json()) as T;
}

/** Файл вместе с именем, под которым его предложено сохранить. */
export interface DownloadedFile {
  blob: Blob;
  filename: string;
}

/**
 * Файл, собранный сервером.
 *
 * Отдельная функция, а не ссылка `<a href>` в разметке: по переходу браузер не приложит
 * ни одного нашего заголовка, и действие уйдёт неподписанным — в журнале выгрузка
 * окажется анонимной. Поэтому файл забирается обычным запросом, с тем же заголовком
 * режима, что и всё остальное.
 *
 * Собирает файл по-прежнему сервер: выгрузка — одна из трёх точек выхода наружу, и
 * проверка `share_externally` стоит там, внутри функции выдачи (ADR-0024). Здесь только
 * сохранение того, что пришло.
 */
export async function requestFile(
  path: string,
  query?: RequestOptions['query'],
): Promise<DownloadedFile> {
  const headers: Record<string, string> = {};
  headers[ACTOR_HEADER] = readActor();

  const response = await fetch(`${API_PREFIX}${path}${buildQuery(query)}`, { headers });

  if (!response.ok) {
    const problem = await safeProblem(response);
    throw new HttpError(response.status, problem);
  }

  return {
    blob: await response.blob(),
    filename: filenameFrom(response.headers.get('Content-Disposition')),
  };
}

/** Имя файла из заголовка. Своё имя придумывается только когда сервер его не прислал. */
function filenameFrom(disposition: string | null): string {
  const match = /filename="?([^";]+)"?/.exec(disposition ?? '');
  return match?.[1] ?? 'orbita.csv';
}

/**
 * Пустые значения в строку запроса не попадают.
 *
 * Иначе адрес обрастает `status_code=&priority_code=`, и по нему нельзя понять, что
 * именно отфильтровано, — а адрес здесь то, чем делятся и что сохраняют в закладки.
 */
function buildQuery(query: RequestOptions['query']): string {
  if (!query) return '';

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === '') continue;
    params.set(key, String(value));
  }

  const search = params.toString();
  return search === '' ? '' : `?${search}`;
}

/** Сервер отвечает по RFC 9457, но упавший сервер отвечает чем угодно. */
async function safeProblem(response: Response): Promise<ProblemDetails> {
  try {
    return (await response.json()) as ProblemDetails;
  } catch {
    return { title: response.statusText };
  }
}
