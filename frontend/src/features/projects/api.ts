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

export interface Project {
  id: string;
  code: string;
  title: string;
  status_code: string;
  priority_code: string;
  direction_id: string;
  due_on: string;
  status_reason: string | null;
  progress_pct: number;
  impediment: string | null;
  impediment_updated_at: string | null;
  impediment_is_stale: boolean;
  impediment_is_active: boolean;
  health: Health;
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

export function fetchDictionaries(): Promise<Dictionaries> {
  return request<Dictionaries>('/dictionaries');
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
