/**
 * Фото из Захвата (ТЗ 7, V18): снимок сжимается в браузере перед отправкой.
 *
 * Камера iPhone даёт 12 Мп, 3–8 МБ на снимок. По 4G это десятки секунд загрузки, а для
 * «доска после совещания» или «визитка» хватает 2048 точек по длинной стороне — около
 * 0,5 МБ. Не вышло сжать (старый браузер, повреждённый файл) — уходит исходник: сервер
 * примет до 20 МБ (`backend/app/domain/files.py`, PHOTO_MAX_SIZE).
 */

import { request } from '@/shared/api/client';
import { uploadTo, type UploadTarget } from '@/shared/api/upload';
import type { PhotoOwnerType } from '@/shared/ui/Photos';

/** Длинная сторона после сжатия: больше глаз на экране телефона и ноутбука не различит. */
const MAX_SIDE = 2048;
const QUALITY = 0.85;

export interface PhotoOwner {
  owner_type: PhotoOwnerType;
  owner_id: string;
}

export async function shrink(file: File): Promise<Blob> {
  if (typeof createImageBitmap !== 'function') return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext('2d');
    if (!context) return file;
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', QUALITY),
    );
    // Сжатое тяжелее исходника — бывает с маленьким PNG: тогда исходник.
    return blob && blob.size < file.size ? blob : file;
  } catch {
    return file;
  }
}

/** Имя файла после сжатия: расширение — по тому, что уходит на самом деле. */
function nameOf(file: File, body: Blob): string {
  if (body === file) return file.name || 'photo.jpg';
  const base = (file.name || 'photo').replace(/\.[^.]+$/, '');
  return `${base}.jpg`;
}

/** Фото к записи: сжать, взять ссылку у API, положить по ней файл, подтвердить. */
export async function attachPhoto(owner: PhotoOwner, file: File): Promise<void> {
  const body = await shrink(file);
  const started = await request<{ file_id: string; upload: UploadTarget }>('/api/v1/files/photos', {
    method: 'POST',
    body: {
      ...owner,
      name: nameOf(file, body),
      content_type: body.type || file.type || 'image/jpeg',
      size: body.size,
    },
  });
  await uploadTo(started.file_id, started.upload, body);
}
