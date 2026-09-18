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
  description: string | null;
  assignee_person_id: string | null;
  status: TaskStatus;
  priority_code: string;
  /**
   * Действующий срок, с учётом продлений. У поручения (`is_control`) им владеет SETA:
   * она принимает продления и закрытия
   * ([ADR-0015](../../../../docs/adr/ADR-0015-seta-data-ownership.md)).
   */
  due_at: string | null;
  /**
   * Плановый срок по проекту — **наш всегда**, SETA им не владеет никогда.
   *
   * Два срока вместо одного заведены сознательно: продление, пришедшее снаружи, не
   * должно затирать план, иначе на вопрос «на сколько это уже сдвинулось» ответить
   * нечем. Просрочку считают по `due_at`, а не по нему (ADR-0004).
   */
  planned_due_at: string | null;
  completed_at: string | null;
  is_control: boolean;
  is_overdue: boolean;
  days_overdue: number;
  checklist_done: number;
  checklist_total: number;
  /** Доля выполненного или `null`, когда чек-листа нет. Считает сервер, не мы. */
  checklist_percent: number | null;
}

/**
 * Что уходит на сервер при создании и правке.
 *
 * Посчитанных полей здесь нет: `is_overdue`, `days_overdue` и доля чек-листа считает
 * сервер, а `completed_at` и `started_at` ставит он же по смене статуса. Форма, которая
 * их отправляет, однажды затрёт расчёт своим устаревшим значением. `code` тоже не здесь:
 * человекочитаемый номер выдаёт сервер.
 */
export interface TaskDraft {
  title: string;
  description: string | null;
  project_id: string | null;
  assignee_person_id: string | null;
  status: TaskStatus;
  priority_code: string;
  due_at: string | null;
  planned_due_at: string | null;
  is_control: boolean;
}

export interface Person {
  id: string;
  full_name: string;
}

export interface ChecklistItem {
  id: string;
  task_id: string;
  text: string;
  is_done: boolean;
  sort_order: number;
}

export interface Tag {
  id: string;
  name: string;
}

export function fetchTasks(filters: Record<string, string>): Promise<Task[]> {
  return request<Task[]>('/tasks', { query: filters });
}

export function fetchPeople(): Promise<Person[]> {
  return request<Person[]>('/people');
}

export function fetchTask(id: string): Promise<Task> {
  return request<Task>(`/tasks/${id}`);
}

export function createTask(draft: TaskDraft): Promise<Task> {
  return request<Task>('/tasks', { method: 'POST', body: draft });
}

export function updateTask(id: string, draft: Partial<TaskDraft>): Promise<Task> {
  return request<Task>(`/tasks/${id}`, { method: 'PATCH', body: draft });
}

// --- Чек-лист ---

export function fetchChecklist(taskId: string): Promise<ChecklistItem[]> {
  return request<ChecklistItem[]>(`/tasks/${taskId}/checklist`);
}

export function addChecklistItem(taskId: string, text: string): Promise<ChecklistItem> {
  return request<ChecklistItem>(`/tasks/${taskId}/checklist`, { method: 'POST', body: { text } });
}

export function patchChecklistItem(
  itemId: string,
  patch: { text?: string; is_done?: boolean },
): Promise<ChecklistItem> {
  return request<ChecklistItem>(`/checklist-items/${itemId}`, { method: 'PATCH', body: patch });
}

export function deleteChecklistItem(itemId: string): Promise<void> {
  return request<void>(`/checklist-items/${itemId}`, { method: 'DELETE' });
}

// --- Теги ---

export function fetchTags(): Promise<Tag[]> {
  return request<Tag[]>('/tags');
}

export function fetchTaskTags(taskId: string): Promise<Tag[]> {
  return request<Tag[]>(`/tasks/${taskId}/tags`);
}

/**
 * Набор тегов задачи целиком, а не «добавь этот, убери тот».
 *
 * Так устроен и сервер (`TaskTags` в `api/routes/checklists.py`): два запроса «добавить»
 * и «убрать» оставили бы задачу в состоянии, которого человек не выбирал, если второй не
 * дошёл.
 */
export function setTaskTags(taskId: string, names: string[]): Promise<Tag[]> {
  return request<Tag[]>(`/tasks/${taskId}/tags`, { method: 'PUT', body: { names } });
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
