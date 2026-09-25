/**
 * Запросы к ORBITA и их типы.
 *
 * Типы описаны руками по схемам ответов бэкенда (pydantic-модели в `backend/app/api/routes`).
 * Автоматической сверки со схемой OpenAPI нет, поэтому схема ответа и тип здесь правятся
 * одним изменением: расхождение поля — это не ошибка типа, а пустая графа на экране у
 * руководителя.
 */

import { request } from './client';

export type Role = 'assistant' | 'leader';

export interface CurrentUser {
  id: string;
  full_name: string;
  role: Role;
  locale: string;
  timezone: string;
  can_write: boolean;
}

export interface Health {
  status: 'ok';
  commit: string;
  env: string;
  time: string;
}

export interface AccessLink {
  url: string;
  issued_at: string;
}

export interface DeviceSession {
  user_agent: string | null;
  ip: string | null;
  last_seen_at: string | null;
  expires_at: string;
}

export interface LocalizedNames {
  ru: string;
  uz_cyrl: string;
  uz_latn: string;
}

export interface DictionaryEntry {
  id: string;
  code: string;
  name: LocalizedNames;
  sort_order: number;
  is_active: boolean;
}

/** Статус: цвет и терминальность — данные справочника, а не код (ТЗ 3.9). */
export interface StatusEntry extends DictionaryEntry {
  color: string;
  is_terminal: boolean;
}

export interface ProjectStatusEntry extends StatusEntry {
  /** Переход в этот статус требует причины. */
  requires_reason: boolean;
}

/** Ответ `/api/v1/dictionaries` — `DictionariesResponse` в `routes/dictionaries.py`. */
export interface Dictionaries {
  project_types: DictionaryEntry[];
  task_types: DictionaryEntry[];
  directions: DictionaryEntry[];
  regions: DictionaryEntry[];
  project_statuses: ProjectStatusEntry[];
  task_statuses: StatusEntry[];
}

export const api = {
  /** Кто открыл систему. Первый запрос после загрузки. */
  me: () => request<CurrentUser>('/api/me'),

  /** Живость и выложенный коммит. Показывается в «Управлении». */
  health: () => request<Health>('/api/health'),

  /** Справочники: ими проверяется, что рабочая база наполнена (критерий приёмки блока 0). */
  dictionaries: () => request<Dictionaries>('/api/v1/dictionaries'),

  /** Перевыпуск личной ссылки. Прежние сессии гаснут сразу. */
  reissueLink: (role: Role) => request<AccessLink>(`/api/access/links/${role}`, { method: 'POST' }),

  /** Устройства, с которых открыт доступ. Чужой вход виден лишней строкой. */
  sessions: (role: Role) => request<DeviceSession[]>(`/api/access/sessions/${role}`),
};
