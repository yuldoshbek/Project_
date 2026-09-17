/**
 * Обращения к API портфеля.
 *
 * Типы описывают то, что действительно приходит, а не то, что хочется получить: поля
 * `health`, `impediment_is_stale` и `impediment_is_active` считаются на сервере и в
 * таблице не хранятся (ADR-0005, ADR-0016). Повторять их расчёт здесь запрещено —
 * второе место с тем же правилом однажды разойдётся с первым.
 */

import { request } from '../../shared/api/client';

export type Health = 'green' | 'yellow' | 'red' | 'grey';

/** Проект или мини-проект (ТЗ 6.1). Мини-проект не требует вех. */
export type ProjectKind = 'project' | 'mini';

/** Откуда берётся процент: `auto` — доля выполненных задач, `manual` — ставит куратор. */
export type ProgressMode = 'auto' | 'manual';

export interface Project {
  id: string;
  code: string;
  title: string;
  description: string | null;
  kind: ProjectKind;
  /**
   * Можно ли показывать проект наружу — не гриф секретности
   * ([ADR-0024](../../../../docs/adr/ADR-0024-share-externally.md)). Точек выхода пять:
   * Google-календарь, SETA, Telegram через её бота, экспорт, внешняя модель.
   */
  share_externally: boolean;
  direction_id: string;
  curator_person_id: string | null;
  status_code: string;
  status_reason: string | null;
  priority_code: string;
  started_on: string;
  due_on: string;
  finished_on: string | null;
  progress_pct: number;
  progress_mode: ProgressMode;
  budget_note: string | null;
  impediment: string | null;
  impediment_updated_at: string | null;
  impediment_is_stale: boolean;
  impediment_is_active: boolean;
  health: Health;
}

/**
 * Что уходит на сервер при создании и правке.
 *
 * Отдельный тип, а не `Partial<Project>`: посчитанных полей здесь быть не должно вовсе.
 * `health`, `progress_pct` в режиме `auto` и признаки помехи считает сервер, и форма,
 * которая их отправляет, однажды затрёт расчёт своим устаревшим значением. `code` тоже
 * не здесь — человекочитаемый номер выдаёт сервер.
 */
export interface ProjectDraft {
  title: string;
  description: string | null;
  kind: ProjectKind;
  share_externally: boolean;
  direction_id: string;
  curator_person_id: string | null;
  status_code: string;
  status_reason: string | null;
  priority_code: string;
  started_on: string;
  due_on: string;
  finished_on: string | null;
  progress_pct: number;
  progress_mode: ProgressMode;
  budget_note: string | null;
}

/** Сотрудник агентства. Не пользователь системы: их двое, а кураторов десятки. */
export interface Person {
  id: string;
  full_name: string;
  position: string | null;
  department: string | null;
}

export interface LocalizedNames {
  ru: string;
  uz_cyrl: string;
  uz_latn: string;
}

export interface DictionaryItem {
  id: string;
  code: string;
  name: LocalizedNames;
}

/**
 * Статус проекта вместе с его правилом.
 *
 * `requires_reason` приходит с сервера, а не записан здесь списком «пауза и отмена»:
 * правило живёт в домене (ТЗ 7), и второй его экземпляр в интерфейсе однажды
 * разошёлся бы с первым — доска перестала бы спрашивать причину, а сервер продолжал бы
 * её требовать, и каждый перенос заканчивался бы отказом.
 */
export interface ProjectStatusEntry extends DictionaryItem {
  requires_reason: boolean;
}

export interface Dictionaries {
  directions: DictionaryItem[];
  project_statuses: ProjectStatusEntry[];
  task_statuses: DictionaryItem[];
  priorities: DictionaryItem[];
}

export function fetchProjects(filters: Record<string, string>): Promise<Project[]> {
  return request<Project[]>('/projects', { query: filters });
}

/**
 * Справочники.
 *
 * `includeInactive` нужен при правке старой записи: иначе направление, выведенное из
 * обращения, исчезнет из списка, и форма молча предложит сохранить проект с другим —
 * или без него. Форма создания недействующие значения не предлагает.
 */
export function fetchDictionaries(includeInactive = false): Promise<Dictionaries> {
  return request<Dictionaries>('/dictionaries', { query: { active_only: !includeInactive } });
}

export function fetchProject(id: string): Promise<Project> {
  return request<Project>(`/projects/${id}`);
}

/**
 * Сотрудники для выбора куратора.
 *
 * Отдельным запросом, а не полем справочников: справочники приходят при открытии любого
 * экрана, а список сотрудников растёт и утяжелял бы каждое такое открытие
 * (`app/api/routes/people.py`).
 *
 * `active_only=false` — при правке старой записи: иначе куратор, которого уже перевели,
 * исчезнет из списка, и форма молча предложит сохранить проект без куратора.
 */
export function fetchPeople(includeInactive = false): Promise<Person[]> {
  return request<Person[]>('/people', { query: { active_only: !includeInactive } });
}

/**
 * Тело запроса из значений формы.
 *
 * Одно место на создание и правку: два тела под одним смыслом разойдутся на первом же
 * новом поле. Уходит всё, что есть в форме, а не только изменённое — сервер различает
 * «не прислали» и «прислали `null`» по `model_fields_set`, и частичная отправка была бы
 * здесь уместнее, но форма показывает все поля сразу, и человек, стёрший срок
 * завершения, ожидает, что он стёрся.
 *
 * Единственное исключение — `progress_pct` в режиме `auto`: его считает сервер по доле
 * выполненных задач, и отправка своего значения затёрла бы расчёт. Запретить это на
 * сервере нечем: правило про режим живёт в том, как процент пересчитывается, а не в
 * проверке входа.
 */
function bodyOf(draft: ProjectDraft): Record<string, unknown> {
  const body: Record<string, unknown> = { ...draft };
  if (draft.progress_mode === 'auto') delete body.progress_pct;
  return body;
}

export function createProject(draft: ProjectDraft): Promise<Project> {
  return request<Project>('/projects', { method: 'POST', body: bodyOf(draft) });
}

export function updateProject(id: string, draft: ProjectDraft): Promise<Project> {
  return request<Project>(`/projects/${id}`, { method: 'PATCH', body: bodyOf(draft) });
}

/**
 * Перенос в другой статус.
 *
 * Причина уходит только тогда, когда её спросили: отправка пустой причины вместе с
 * переносом «в работу» стёрла бы причину прошлой паузы, а она — история проекта.
 */
export function updateProjectStatus(id: string, status: string, reason?: string): Promise<Project> {
  const body: Record<string, string> = { status_code: status };
  if (reason !== undefined) body.status_reason = reason;
  return request<Project>(`/projects/${id}`, { method: 'PATCH', body });
}

/** Название из справочника на языке интерфейса. */
export function localizedName(names: LocalizedNames, language: string): string {
  if (language === 'uz-Cyrl') return names.uz_cyrl;
  if (language === 'uz-Latn') return names.uz_latn;
  return names.ru;
}
