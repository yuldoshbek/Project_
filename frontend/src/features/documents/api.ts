/**
 * Обращения к API вложений (ORB-017).
 *
 * **Содержимое сюда не приходит.** Сервер отдаёт подписанную ссылку в хранилище, а
 * браузер идёт по ней сам ([ADR-0009](../../../../docs/adr/ADR-0009-attachments.md)).
 * Поэтому здесь нет ни одной функции, возвращающей байты: ссылка кладётся в `src` у
 * `<img>` или `<iframe>`, и файл показывается, не пройдя через приложение.
 *
 * Ссылка живёт считанные минуты и берётся каждый раз заново. Хранить её в состоянии
 * экрана нельзя: вкладку оставляют открытой на час, и сохранённая ссылка к этому
 * времени — это картинка, которая перестала рисоваться без единого сообщения.
 */

import { request, requestUpload } from '../../shared/api/client';

export type DocumentTarget = 'project' | 'task';

/** Что показывать вместо файла. Состояния считает сервер, не мы. */
export type PreviewState = 'native' | 'pending' | 'ready' | 'failed' | 'unsupported';

export interface DocumentVersion {
  id: string;
  number: number;
  size_bytes: number;
  content_type: string;
  sha256: string;
  uploaded_at: string;
  uploaded_by: string | null;
  preview_state: PreviewState;
}

export interface Attachment {
  id: string;
  entity_type: DocumentTarget;
  entity_id: string;
  name: string;
  current_version: number;
  created_at: string;
  version: DocumentVersion;
}

export interface UploadResult {
  /** `false` — этот файл уже приложен, и новой версии не появилось. */
  created: boolean;
  document: Attachment;
}

export interface DocumentLink {
  url: string;
  expires_in: number;
  filename: string;
}

export function fetchAttachments(target: DocumentTarget, entityId: string): Promise<Attachment[]> {
  return request<Attachment[]>('/documents', {
    query: { entity_type: target, entity_id: entityId },
  });
}

export function fetchVersions(documentId: string): Promise<DocumentVersion[]> {
  return request<DocumentVersion[]>(`/documents/${documentId}/versions`);
}

export function uploadAttachment(
  target: DocumentTarget,
  entityId: string,
  file: File,
): Promise<UploadResult> {
  const form = new FormData();
  form.set('entity_type', target);
  form.set('entity_id', entityId);
  form.set('file', file);
  return requestUpload<UploadResult>('/documents', form);
}

/**
 * Ссылка на содержимое.
 *
 * `inline` различает «показать» и «сохранить». Для офисного файла показывается
 * производный PDF — браузер таблицу не откроет, — а сохраняется всегда исходный файл:
 * человеку нужна таблица, а не её отпечаток.
 */
export function fetchLink(
  documentId: string,
  options: { inline?: boolean; version?: number } = {},
): Promise<DocumentLink> {
  return request<DocumentLink>(`/documents/${documentId}/link`, {
    query: { inline: options.inline ?? false, version: options.version },
  });
}

export function deleteAttachment(documentId: string): Promise<void> {
  return request<void>(`/documents/${documentId}`, { method: 'DELETE' });
}

/** Размер в том виде, в каком его читают: «1,2 МБ», а не «1258291». */
export function humanSize(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0).replace('.', ',')} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`;
}

/** Показывается ли файл в окне — или для него ещё нет производного PDF. */
export function canShow(state: PreviewState): boolean {
  return state === 'native' || state === 'ready';
}

/** Картинка рисуется `<img>`, остальное — рамкой просмотра PDF. */
export function isImage(contentType: string): boolean {
  return contentType.startsWith('image/');
}
