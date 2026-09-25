/**
 * Причина паузы или отмены (ТЗ 3.1). Без неё статус не меняется: пауза без причины
 * через месяц становится вечной — никто не помнит, чего ждали.
 *
 * Одна форма на два входа: перенос плитки на доске и кнопка в карточке проекта.
 */

import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/shared/ui/Button';

import type { ProjectStatus } from './model';

interface StatusReasonProps {
  status: ProjectStatus;
  title?: string;
  busy: boolean;
  onSave: (reason: string) => void;
  onCancel: () => void;
}

export function StatusReason({ status, title, busy, onSave, onCancel }: StatusReasonProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const inputId = useId();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (text.trim()) onSave(text.trim());
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <p className="text-sm font-semibold text-ink-strong">
        {t('projects.board.moveTo', { status: t(`projects.statuses.${status}`) })}
        {title ? <span className="block font-normal text-ink-muted">{title}</span> : null}
      </p>
      <label htmlFor={inputId} className="text-sm text-ink">
        {t('projects.panel.reasonLabel')}
      </label>
      <textarea
        id={inputId}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={t('projects.panel.reasonPlaceholder')}
        rows={2}
        autoFocus
        className="w-full rounded-[var(--radius)] border border-line-strong bg-card p-2 text-[15px] text-ink"
      />
      <div className="flex gap-2">
        <Button type="submit" look="primary" disabled={busy || !text.trim()}>
          {t('projects.panel.save')}
        </Button>
        <Button type="button" look="quiet" onClick={onCancel}>
          {t('projects.panel.cancel')}
        </Button>
      </div>
    </form>
  );
}
