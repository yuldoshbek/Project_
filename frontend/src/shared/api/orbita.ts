/**
 * Запросы к ORBITA и их типы.
 *
 * Типы описаны здесь руками и сверяются со схемой OpenAPI проверкой `npm run api:check`:
 * расхождение поля между бэкендом и интерфейсом — это не ошибка типа, а пустая графа на
 * экране у руководителя. Генерация полного клиента приедет вместе с разделами данных
 * (блок 1), когда описывать станет что: сейчас запросов четыре, и генератор вокруг них —
 * инструмент дороже задачи.
 */

import { POLL_INTERVAL_MS, request } from './client';

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

export interface Dictionaries {
  directions: DictionaryEntry[];
  project_statuses: DictionaryEntry[];
  task_statuses: DictionaryEntry[];
  priorities: DictionaryEntry[];
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

export { POLL_INTERVAL_MS };
