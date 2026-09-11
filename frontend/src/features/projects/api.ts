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

export interface Dictionaries {
  directions: DictionaryItem[];
  project_statuses: DictionaryItem[];
  task_statuses: DictionaryItem[];
  priorities: DictionaryItem[];
}

export function fetchProjects(filters: Record<string, string>): Promise<Project[]> {
  return request<Project[]>('/projects', { query: filters });
}

export function fetchDictionaries(): Promise<Dictionaries> {
  return request<Dictionaries>('/dictionaries');
}
