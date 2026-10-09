/**
 * Загрузка файла в три шага (ADR-0009): ссылку выдал API, файл — прямо в хранилище по ней,
 * затем API проверяет, что файл лёг. Ссылка S3 — на чужой адрес и без cookie; у локального
 * хранилища (разработка, сервер агентства) это путь API, туда файл идёт с сессией.
 *
 * Общая для версий презентаций и фото из Захвата: два пути загрузки разошлись бы на первой
 * же правке подписи.
 */

import { request } from './client';

export interface UploadTarget {
  url: string;
  method: string;
  headers: Record<string, string>;
}

export async function uploadTo(fileId: string, upload: UploadTarget, body: Blob): Promise<void> {
  if (upload.url.startsWith('/')) {
    await request<void>(upload.url, { method: 'PUT', body });
  } else {
    const response = await fetch(upload.url, {
      method: upload.method,
      headers: upload.headers,
      body,
    });
    if (!response.ok) throw new Error(`upload ${response.status}`);
  }
  await request<void>(`/api/v1/files/${fileId}/complete`, { method: 'POST' });
}

/** Ссылка на просмотр: подписанная и короткоживущая, поэтому — по требованию, а не заранее. */
export async function fileLink(fileId: string): Promise<string> {
  const found = await request<{ url: string }>(`/api/v1/files/${fileId}/link`);
  return found.url;
}
