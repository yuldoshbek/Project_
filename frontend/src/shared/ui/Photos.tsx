/**
 * Фото записи — то, что приложили из Захвата (ТЗ 7, V18): в карточке задачи, у идеи и у
 * записи во входящих.
 *
 * Нет фото — нет и блока: рамка «Фото: нет» на каждой карточке читалась бы как просьба их
 * добавить. Ссылка на снимок подписанная и короткоживущая (ADR-0009), поэтому берётся при
 * показе и обновляется раньше, чем истечёт.
 */

import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { request } from '@/shared/api/client';
import { fileLink } from '@/shared/api/upload';

export type PhotoOwnerType = 'task' | 'idea' | 'capture';

interface Photo {
  id: string;
  name: string;
}

/** Подписанная ссылка живёт пять минут (`backend/app/adapters/storage`) — берём за минуту до. */
const LINK_FRESH_MS = 4 * 60_000;

export function Photos({ ownerType, ownerId }: { ownerType: PhotoOwnerType; ownerId: string }) {
  const photos = useQuery({
    queryKey: ['photos', ownerType, ownerId],
    queryFn: () =>
      request<Photo[]>(
        `/api/v1/files/photos?owner_type=${ownerType}&owner_id=${encodeURIComponent(ownerId)}`,
      ),
    // Фото не меняются у второго пользователя на глазах: опрос, который стоит у данных
    // разделов, здесь стоил бы запросов впустую. После загрузки их перечитывает Захват.
    refetchInterval: false,
  });

  return <PhotoStrip photos={photos.data ?? []} />;
}

/**
 * Фото, уже пришедшие с данными экрана, — у идей: строка идеи и есть её карточка, и список
 * из пятидесяти идей не должен стоить пятидесяти запросов за фото.
 */
export function PhotoStrip({ photos }: { photos: Photo[] }) {
  const { t } = useTranslation();
  if (photos.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-ink-muted">{t('photos.title')}</p>
      <ul className="mt-1 flex flex-wrap gap-2">
        {photos.map((photo) => (
          <Thumb key={photo.id} photo={photo} />
        ))}
      </ul>
    </div>
  );
}

function Thumb({ photo }: { photo: Photo }) {
  const { t } = useTranslation();
  const link = useQuery({
    queryKey: ['file-link', photo.id],
    queryFn: () => fileLink(photo.id),
    staleTime: LINK_FRESH_MS,
    refetchInterval: LINK_FRESH_MS,
  });
  return (
    <li>
      <a
        href={link.data}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={t('photos.open', { name: photo.name })}
        className="block size-20 overflow-hidden rounded-[var(--radius)] border border-line bg-sunken"
      >
        {link.data ? (
          <img src={link.data} alt="" loading="lazy" className="size-full object-cover" />
        ) : null}
      </a>
    </li>
  );
}
