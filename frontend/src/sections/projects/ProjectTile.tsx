/**
 * Плитка проекта — карточка на доске и в списке на телефоне.
 *
 * Отвечает на три вопроса раздела (ТЗ 5) без раскрытия: идёт или стоит (ступень и
 * отклонение), что мешает (строка с возрастом), что держит Центр (роль Центра). Остальное
 * — в карточке проекта по касанию.
 */

import { AlertTriangle, Building2, Layers } from 'lucide-react';
import type { DragEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { deviationText } from '@/sections/pult/text';
import { STEP_SIGNAL } from '@/sections/pult/model';
import { cn } from '@/shared/lib/cn';
import { Signal } from '@/shared/ui/Signal';

import type { ProjectCard } from './model';
import { dueText, lagText } from './text';

interface ProjectTileProps {
  card: ProjectCard;
  onOpen: (id: string) => void;
  /** Доска: плитку можно перетащить в другую колонку. */
  draggable?: boolean;
}

export function ProjectTile({ card, onOpen, draggable = false }: ProjectTileProps) {
  const { t } = useTranslation();
  const terminal = card.status === 'done' || card.status === 'cancelled';

  const onDragStart = (event: DragEvent) => {
    event.dataTransfer.setData('text/plain', card.id);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <article
      draggable={draggable}
      onDragStart={draggable ? onDragStart : undefined}
      className={cn(
        'rounded-[var(--radius)] border border-line bg-card shadow-card',
        'transition-colors duration-[var(--motion-fast)] hover:border-line-accent',
        draggable && 'cursor-grab active:cursor-grabbing',
        terminal && 'opacity-75',
      )}
    >
      <button
        type="button"
        onClick={() => onOpen(card.id)}
        className="flex w-full min-w-0 flex-col gap-1.5 p-3 text-left"
      >
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {card.step ? (
            <>
              <Signal state={STEP_SIGNAL[card.step]}>{t(`pult.steps.${card.step}`)}</Signal>
              <span className="numeric text-xs font-medium text-ink">
                {deviationText(t, { step: card.step, deviation: card.deviation })}
              </span>
            </>
          ) : null}
          <span className="numeric ml-auto text-xs text-ink-muted">{card.code}</span>
        </span>

        <span className="line-clamp-2 text-[15px] leading-snug font-medium text-ink-strong">
          {card.title}
        </span>

        <span className="truncate text-xs text-ink-muted">
          {[card.responsible?.name ?? t('projects.card.noHolder'), card.type.name].join(' · ')}
        </span>

        <span className="numeric text-xs text-ink">{dueText(t, card)}</span>

        {!terminal ? (
          <span className="flex items-center gap-2">
            <span
              className="h-1.5 flex-1 overflow-hidden rounded-[var(--radius-pill)] bg-sunken"
              aria-hidden="true"
            >
              <span
                className="block h-full rounded-[var(--radius-pill)] bg-accent"
                style={{ width: `${card.readiness}%` }}
              />
            </span>
            <span className="numeric text-xs text-ink-muted">
              {t('projects.card.readiness', { value: card.readiness })}
            </span>
          </span>
        ) : null}

        {/* У паузы и отмены вместо отставания — причина: «отстаёт на 30 дн» у проекта,
            который остановили нарочно, ничего не говорит, а причина говорит, чего ждём. */}
        {card.status_reason ? (
          <span className="line-clamp-2 text-xs text-ink">
            {t('projects.card.reason', { reason: card.status_reason })}
          </span>
        ) : !terminal ? (
          <span className={cn('text-xs', card.lag_days > 0 ? 'text-wait-ink' : 'text-ink-muted')}>
            {lagText(t, card.lag_days)}
          </span>
        ) : null}

        {card.impediment && !card.impediment.stale ? (
          <span className="flex items-start gap-1.5 rounded-[var(--radius-sm)] bg-wait-soft px-2 py-1 text-xs text-wait-ink">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span className="line-clamp-2">{card.impediment.text}</span>
          </span>
        ) : null}

        {card.center_role || card.is_multiyear ? (
          <span className="flex flex-wrap gap-1.5">
            {card.is_multiyear ? (
              <span className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-accent-soft px-2 py-0.5 text-xs text-accent-ink">
                <Layers className="size-3" aria-hidden="true" />
                {t('projects.card.program')}
              </span>
            ) : null}
            {card.center_role ? (
              <span className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-sunken px-2 py-0.5 text-xs text-ink">
                <Building2 className="size-3" aria-hidden="true" />
                {t('projects.card.center', { role: t(`projects.roles.${card.center_role}`) })}
              </span>
            ) : null}
          </span>
        ) : null}
      </button>
    </article>
  );
}
