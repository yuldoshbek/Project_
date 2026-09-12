/**
 * Ящик с вложениями поверх списка.
 *
 * **Временная дверь, а не экран.** Место вложений — карточка проекта (ORB-018) и карточка
 * задачи (ORB-022): там они стоят рядом с вехами, обсуждением и лентой событий. Карточек
 * пока нет, а проверить загрузку, версии и предпросмотр нужно на живой системе, а не
 * только тестом. Поэтому в строку списка добавлена скрепка, открывающая эту панель.
 *
 * Когда карточки появятся, `Attachments` переедет туда как есть — панель ничего не знает
 * о том, из чего её открыли. Уйдёт только скрепка и этот файл.
 *
 * Закрытие по Escape и по щелчку вне — не украшение: ящик перекрывает список целиком, и
 * без очевидного выхода из него человек перезагружает страницу.
 */

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { Attachments } from './Attachments';
import styles from './documents.module.css';
import type { DocumentTarget } from './api';

export interface AttachmentsDrawerProps {
  target: DocumentTarget;
  entityId: string;
  /** Название записи — заголовок ящика: без него непонятно, чьи это файлы. */
  title: string;
  onClose: () => void;
}

export function AttachmentsDrawer({ target, entityId, title, onClose }: AttachmentsDrawerProps) {
  const { t } = useTranslation();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return (
    <>
      {/* Подложка закрывает ящик щелчком. Роль кнопки — чтобы это не было действием,
          доступным только мыши: по клавиатуре из ящика выходят по Escape, и подложка в
          порядке обхода была бы лишней остановкой. */}
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />
      <aside
        className={styles.drawer}
        role="dialog"
        aria-modal="true"
        aria-label={t('documents.drawerLabel', { name: title })}
      >
        <header className={styles.drawerHead}>
          <h2 className={styles.drawerTitle}>{title}</h2>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label={t('documents.close')}
          >
            {/* Значок, а не знак «✕» текстом: текст в разметке обязан переводиться, а
                крестик переводить нечем — и линтер справедливо на это указывает. */}
            <svg
              width={16}
              height={16}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
              aria-hidden="true"
              focusable="false"
            >
              <path d="M6 6 18 18M18 6 6 18" />
            </svg>
          </button>
        </header>
        <Attachments target={target} entityId={entityId} />
      </aside>
    </>
  );
}

/** Скрепка в строке списка: единственный способ попасть в ящик. */
export function AttachmentsButton({ onOpen, label }: { onOpen: () => void; label: string }) {
  return (
    <button type="button" className={styles.clip} onClick={onOpen} aria-label={label}>
      <svg
        width={20}
        height={20}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M20 11.5 12.4 19a4.5 4.5 0 0 1-6.4-6.4l7.8-7.8a3 3 0 0 1 4.2 4.2l-7.7 7.7a1.5 1.5 0 0 1-2.1-2.1l7-7" />
      </svg>
    </button>
  );
}
