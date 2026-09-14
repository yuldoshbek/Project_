/**
 * Причина паузы или отмены.
 *
 * **Спрашивается до переноса, а не после.** Сервер без причины перенос не примет (ТЗ 7), и
 * перенести карточку, чтобы через секунду вернуть её с отказом, — значит показать
 * человеку, что система передумала. Отказ от ввода оставляет карточку на месте, и
 * запрос не уходит вовсе.
 *
 * Причина нужна не для отчёта: через месяц никто не помнит, чего ждёт приостановленный
 * проект, и снять паузу некому.
 */

import type { FormEvent } from 'react';
import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Project } from './api';
import styles from './board.module.css';

export interface ReasonDialogProps {
  project: Project;
  statusName: string;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

export function ReasonDialog({ project, statusName, onConfirm, onCancel }: ReasonDialogProps) {
  const { t } = useTranslation();
  const [reason, setReason] = useState('');
  const field = useRef<HTMLTextAreaElement>(null);
  const titleId = useId();
  const fieldId = useId();
  const hintId = useId();

  useEffect(() => {
    field.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
    };
  }, [onCancel]);

  const cleaned = reason.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (cleaned !== '') onConfirm(cleaned);
  };

  return (
    <>
      <div className={styles.backdrop} onClick={onCancel} aria-hidden="true" />
      <form
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onSubmit={submit}
      >
        <h2 id={titleId} className={styles.dialogTitle}>
          {t('projects.board.reasonTitle', { status: statusName })}
        </h2>
        <p className={styles.dialogProject}>
          <span className={styles.code}>{project.code}</span>
          <span>{project.title}</span>
        </p>

        <label htmlFor={fieldId} className={styles.dialogLabel}>
          {t('projects.board.reasonLabel')}
        </label>
        <textarea
          id={fieldId}
          ref={field}
          className={styles.reasonField}
          rows={3}
          value={reason}
          aria-describedby={hintId}
          onChange={(event) => {
            setReason(event.target.value);
          }}
        />
        <p id={hintId} className={styles.dialogHint}>
          {t('projects.board.reasonHint')}
        </p>

        <div className={styles.dialogActions}>
          <button type="button" className={styles.secondary} onClick={onCancel}>
            {t('projects.board.reasonCancel')}
          </button>
          <button type="submit" className={styles.primary} disabled={cleaned === ''}>
            {t('projects.board.reasonConfirm')}
          </button>
        </div>
      </form>
    </>
  );
}
