/**
 * Вложения записи (ORB-017).
 *
 * Панель, а не экран: она встраивается в карточку проекта (ORB-018) и карточку задачи
 * (ORB-022), когда те появятся. Пока карточек нет, попасть сюда можно из списка — по
 * скрепке в строке.
 *
 * **Предпросмотр показывается здесь, а не в новой вкладке.** Требование ТЗ 6.6 — увидеть
 * файл, не скачивая его; открытая вкладка с адресом хранилища этому формально
 * удовлетворяет, но на деле означает «скачать в браузер и посмотреть там». Здесь файл
 * рисуется в самой панели, рядом со списком, откуда его открыли.
 *
 * **Ссылка берётся заново на каждый показ.** Она живёт минуты (для закрытых проектов —
 * минуту), и сохранённая в состоянии экрана ссылка через час превращается в картинку,
 * которая перестала рисоваться, ничего об этом не сообщив.
 *
 * **Пока строится производный PDF, список перечитывается.** Иначе загруженная таблица
 * навсегда остаётся с надписью «предпросмотр готовится»: задание своё отработало, а
 * экран об этом не узнал.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { DragEvent } from 'react';
import { useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { HttpError } from '../../shared/api/client';
import { useSession } from '../../shared/auth/useSession';
import { formatDateTime } from '../../shared/time';
import { EmptyState } from '../../shared/ui/EmptyState';
import { ErrorState } from '../../shared/ui/ErrorState';
import { Skeleton } from '../../shared/ui/Skeleton';
import styles from './documents.module.css';
import type { Attachment, DocumentTarget, PreviewState } from './api';
import {
  canShow,
  deleteAttachment,
  fetchAttachments,
  fetchLink,
  fetchVersions,
  humanSize,
  isImage,
  uploadAttachment,
} from './api';

/** Как часто перечитывать список, пока хоть у одного файла строится предпросмотр. */
const WHILE_CONVERTING_MS = 3000;

export interface AttachmentsProps {
  target: DocumentTarget;
  entityId: string;
}

export function Attachments({ target, entityId }: AttachmentsProps) {
  const { t } = useTranslation();
  const { profile } = useSession();
  const client = useQueryClient();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const [opened, setOpened] = useState<string | null>(null);
  const [showVersionsOf, setShowVersionsOf] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const mayEdit = profile?.role === 'assistant';
  const key = ['documents', target, entityId];

  const list = useQuery({
    queryKey: key,
    queryFn: () => fetchAttachments(target, entityId),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((item) => item.version.preview_state === 'pending')
        ? WHILE_CONVERTING_MS
        : false,
  });

  const upload = useMutation({
    mutationFn: (file: File) => uploadAttachment(target, entityId, file),
    onSuccess: async (result) => {
      setNotice(
        result.created ? null : t('documents.alreadyAttached', { name: result.document.name }),
      );
      await client.invalidateQueries({ queryKey: key });
    },
    onError: (error: unknown) => {
      // Сообщения сервера обращены к тому, кто загружает: «файл весит 62,0 МБ, а предел —
      // 50,0 МБ». Заменять их своим «ошибка загрузки» значит выбрасывать единственное,
      // что объясняет отказ.
      setNotice(error instanceof HttpError ? error.message : t('documents.uploadFailed'));
    },
  });

  const remove = useMutation({
    mutationFn: (documentId: string) => deleteAttachment(documentId),
    onSuccess: async () => {
      setOpened(null);
      await client.invalidateQueries({ queryKey: key });
    },
  });

  const send = (files: FileList | null) => {
    setNotice(null);
    for (const file of Array.from(files ?? [])) upload.mutate(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (mayEdit) send(event.dataTransfer.files);
  };

  return (
    <section className={styles.panel} aria-label={t('documents.title')}>
      <header className={styles.head}>
        <h3 className={styles.heading}>{t('documents.title')}</h3>
        {list.data !== undefined && (
          <span className={styles.count}>{t('documents.count', { count: list.data.length })}</span>
        )}
      </header>

      {mayEdit && (
        <div
          className={dragging ? `${styles.dropZone} ${styles.dropActive}` : styles.dropZone}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => {
            setDragging(false);
          }}
          onDrop={onDrop}
        >
          <label className={styles.dropLabel} htmlFor={inputId}>
            {t('documents.dropHere')}
          </label>
          <input
            id={inputId}
            ref={inputRef}
            className={styles.fileInput}
            type="file"
            multiple
            onChange={(event) => {
              send(event.target.files);
              event.target.value = '';
            }}
          />
          {upload.isPending && <span className={styles.uploading}>{t('documents.uploading')}</span>}
        </div>
      )}

      {notice !== null && (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      )}

      {list.isPending && <Skeleton count={3} />}
      {list.isError && (
        <ErrorState
          titleKey="documents.loadFailed"
          hintKey="documents.loadFailedHint"
          onRetry={() => {
            void list.refetch();
          }}
        />
      )}
      {list.data?.length === 0 && (
        <EmptyState titleKey="documents.empty" hintKey="documents.emptyHint" />
      )}

      <ul className={styles.list}>
        {(list.data ?? []).map((item) => (
          <li key={item.id} className={styles.item}>
            <div className={styles.row}>
              <span className={styles.name}>{item.name}</span>
              <span className={styles.meta}>
                {item.current_version > 1 && (
                  <span className={styles.version}>
                    {t('documents.version', { number: item.current_version })}
                  </span>
                )}
                <span>{humanSize(item.version.size_bytes)}</span>
              </span>
            </div>

            <div className={styles.actions}>
              <ShowButton
                document={item}
                opened={opened === item.id}
                onToggle={() => {
                  setOpened(opened === item.id ? null : item.id);
                }}
              />
              <DownloadButton document={item} />
              {item.current_version > 1 && (
                <button
                  type="button"
                  className={styles.action}
                  onClick={() => {
                    setShowVersionsOf(showVersionsOf === item.id ? null : item.id);
                  }}
                >
                  {t('documents.versions')}
                </button>
              )}
              {mayEdit && (
                <button
                  type="button"
                  className={`${styles.action} ${styles.danger}`}
                  onClick={() => {
                    remove.mutate(item.id);
                  }}
                >
                  {t('documents.remove')}
                </button>
              )}
            </div>

            {showVersionsOf === item.id && <Versions documentId={item.id} />}
            {opened === item.id && <Preview document={item} />}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Кнопка показа.
 *
 * У файла, чей производный PDF ещё строится, показывать нечего — и кнопка говорит
 * именно это, а не молчит. Пустое место на её месте читается как поломка.
 */
function ShowButton({
  document,
  opened,
  onToggle,
}: {
  document: Attachment;
  opened: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const state: PreviewState = document.version.preview_state;

  if (!canShow(state)) {
    return (
      <span className={styles.pending}>
        {state === 'pending' ? t('documents.previewPending') : t('documents.previewFailed')}
      </span>
    );
  }

  return (
    <button type="button" className={styles.action} onClick={onToggle} aria-expanded={opened}>
      {opened ? t('documents.hide') : t('documents.show')}
    </button>
  );
}

/**
 * Показ файла в самой панели.
 *
 * Ссылка запрашивается при раскрытии и не сохраняется: у неё считанные минуты жизни.
 */
function Preview({ document }: { document: Attachment }) {
  const { t } = useTranslation();
  const link = useQuery({
    queryKey: ['document-link', document.id, document.current_version, 'inline'],
    queryFn: () => fetchLink(document.id, { inline: true }),
    gcTime: 0,
  });

  if (link.isPending) return <Skeleton count={1} height={120} />;
  if (link.isError || link.data === undefined) {
    return <p className={styles.notice}>{t('documents.previewFailed')}</p>;
  }

  return (
    <div className={styles.preview}>
      {isImage(document.version.content_type) ? (
        <img className={styles.image} src={link.data.url} alt={document.name} />
      ) : (
        <iframe className={styles.frame} src={link.data.url} title={document.name} />
      )}
    </div>
  );
}

/**
 * Скачивание.
 *
 * Ссылка берётся запросом и открывается сразу: заголовок с токеном браузер по обычной
 * ссылке не понесёт, а класть токен в адрес нельзя — адрес попадает в журналы и в
 * историю. Открывается всегда исходный файл, а не производный PDF: сохранить человеку
 * нужна таблица.
 */
function DownloadButton({ document: attachment }: { document: Attachment }) {
  const { t } = useTranslation();
  const take = useMutation({
    mutationFn: () => fetchLink(attachment.id),
    onSuccess: (link) => {
      window.open(link.url, '_blank', 'noopener');
    },
  });

  return (
    <button
      type="button"
      className={styles.action}
      onClick={() => {
        take.mutate();
      }}
    >
      {t('documents.download')}
    </button>
  );
}

/** История версий: что было до нынешней и когда её заменили. */
function Versions({ documentId }: { documentId: string }) {
  const { t } = useTranslation();
  const versions = useQuery({
    queryKey: ['document-versions', documentId],
    queryFn: () => fetchVersions(documentId),
  });

  if (versions.isPending) return <Skeleton count={2} />;
  if (versions.isError) return <p className={styles.notice}>{t('documents.loadFailed')}</p>;

  return (
    <ol className={styles.versions}>
      {(versions.data ?? []).map((version) => (
        <li key={version.id} className={styles.versionRow}>
          <span className={styles.version}>
            {t('documents.version', { number: version.number })}
          </span>
          <span>{formatDateTime(version.uploaded_at)}</span>
          <span>{humanSize(version.size_bytes)}</span>
          <VersionLink documentId={documentId} number={version.number} />
        </li>
      ))}
    </ol>
  );
}

function VersionLink({ documentId, number }: { documentId: string; number: number }) {
  const { t } = useTranslation();
  const take = useMutation({
    mutationFn: () => fetchLink(documentId, { version: number }),
    onSuccess: (link) => {
      window.open(link.url, '_blank', 'noopener');
    },
  });

  return (
    <button
      type="button"
      className={styles.action}
      onClick={() => {
        take.mutate();
      }}
    >
      {t('documents.download')}
    </button>
  );
}
