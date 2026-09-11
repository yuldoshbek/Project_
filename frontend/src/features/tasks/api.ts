/**
 * Обращения к API базы задач.
 *
 * `is_overdue`, `days_overdue` и доля чек-листа приходят с сервера и здесь не
 * пересчитываются: каждое из правил вычисляется в одном месте
 * ([ADR-0004](../../../../docs/adr/ADR-0004-overdue-is-computed.md)). Вторая реализация
 * на клиенте разошлась бы с первой, и число «горящих» на экране перестало бы совпадать
 * со сводкой в Telegram.
 */

import type { DownloadedFile } from '../../shared/api/client';
import { request, requestFile } from '../../shared/api/client';

export type TaskStatus = 'new' | 'in_progress' | 'in_review' | 'done' | 'cancelled';

export interface Task {
  id: string;
  code: string;
  project_id: string | null;
  title: string;
  assignee_person_id: string | null;
  status: TaskStatus;
  priority_code: string;
  due_at: string | null;
  completed_at: string | null;
  is_control: boolean;
  is_overdue: boolean;
  days_overdue: number;
  checklist_done: number;
  checklist_total: number;
  /** Доля выполненного или `null`, когда чек-листа нет. Считает сервер, не мы. */
  checklist_percent: number | null;
}

export interface Person {
  id: string;
  full_name: string;
}

export function fetchTasks(filters: Record<string, string>): Promise<Task[]> {
  return request<Task[]>('/tasks', { query: filters });
}

export function fetchPeople(): Promise<Person[]> {
  return request<Person[]>('/people');
}

/**
 * Выгрузка текущей выборки.
 *
 * Файл собирает **сервер**, а не браузер из того, что уже лежит на странице: выгрузка —
 * точка выхода наружу, и задачи закрытых проектов через неё не проходят (ADR-0007).
 * Собери файл здесь — и проверка осталась бы на клиенте, то есть нигде.
 *
 * Те же фильтры, что на экране, уходят в запрос: «выгрузить» значит «выгрузить то, что
 * я вижу», а не «выгрузить всё».
 */
export function fetchTasksFile(filters: Record<string, string>): Promise<DownloadedFile> {
  return requestFile('/tasks/export.csv', filters);
}
