/**
 * Строка задачи — список на всех устройствах.
 *
 * Отвечает на вопрос раздела без раскрытия: что (название), кому (ответственный), к какому
 * сроку (срок и ступень). Остальное — привязка и чек-лист — одной строкой подписи. Статус
 * виден, только если он не «в работе»: в работе — почти все задачи, и слово в каждой строке
 * было бы шумом.
 */

import { CheckSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { STEP_SIGNAL } from '@/sections/pult/model';
import { deviationText } from '@/sections/pult/text';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Signal } from '@/shared/ui/Signal';

import { TERMINAL, type TaskCard } from './model';
import { dueText, linkText } from './text';

interface TaskRowProps {
  task: TaskCard;
  onOpen: (id: string) => void;
  selected?: boolean;
}

export function TaskRow({ task, onOpen, selected = false }: TaskRowProps) {
  const { t } = useTranslation();
  const closed = TERMINAL.has(task.status);
  const link = linkText(t, task);
  const meta = [task.assignee?.name ?? t('tasks.card.noAssignee'), link].filter(Boolean);

  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(task.id)}
        aria-current={selected ? 'true' : undefined}
        className={cn(
          'flex min-h-touch w-full flex-col gap-1 rounded-[var(--radius)] border bg-card px-3 py-2 text-left',
          'transition-colors duration-[var(--motion-fast)] hover:border-line-accent',
          selected ? 'border-line-accent bg-accent-soft/40' : 'border-line',
          closed && 'opacity-75',
        )}
      >
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {task.step ? (
            <>
              <Signal state={STEP_SIGNAL[task.step]}>{t(`pult.steps.${task.step}`)}</Signal>
              <span className="numeric text-xs font-medium text-ink">
                {deviationText(t, { step: task.step, deviation: task.deviation })}
              </span>
            </>
          ) : null}
          {task.status !== 'in_progress' ? (
            <span className="rounded-[var(--radius-pill)] bg-sunken px-2 py-0.5 text-xs text-ink-muted">
              {t(`tasks.statuses.${task.status}`)}
            </span>
          ) : null}
          <span className="numeric ml-auto text-xs text-ink-muted">
            {closed && task.completed_on
              ? t('tasks.card.done', { date: formatDate(task.completed_on) })
              : dueText(t, task)}
          </span>
        </span>

        <span
          className={cn(
            'line-clamp-2 text-[15px] leading-snug font-medium',
            closed ? 'text-ink-muted line-through decoration-ink-muted/50' : 'text-ink-strong',
          )}
        >
          {task.title}
        </span>

        <span className="flex items-center gap-2 text-xs text-ink-muted">
          <span className="min-w-0 flex-1 truncate">{meta.join(' · ')}</span>
          {task.checklist.total > 0 ? (
            <span className="numeric inline-flex shrink-0 items-center gap-1">
              <CheckSquare className="size-3.5" aria-hidden="true" />
              {t('tasks.card.checklist', task.checklist)}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}
