/**
 * Годовые циклы списком — все действующие, по ближайшей дате (ТЗ 11: «годовые циклы»).
 *
 * В сетке цикл виден только своими датами на год вперёд, а у цикла «раз в три года» их два
 * года из трёх нет: без списка такой цикл после записи нельзя было бы ни открыть, ни
 * отменить. Касание строки открывает цикл — правило, даты, отмена.
 */

import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { formatDate } from '@/shared/time';
import { Failure, Loading } from '@/shared/ui/States';

import { KIND_ICON } from './kinds';
import { ruleText } from './text';
import { useCycles } from './useCalendar';

const Icon = KIND_ICON.cycle;

export function CyclesList({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const cycles = useCycles();

  if (cycles.isPending) return <Loading />;
  if (cycles.isError) {
    return <Failure detail={describeError(cycles.error)} onRetry={() => void cycles.refetch()} />;
  }

  return (
    <div className="flex flex-col gap-3">
      <header className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-ink-strong">{t('calendar.cycles.title')}</h2>
        <p className="text-sm text-ink-muted">{t('calendar.cycles.question')}</p>
      </header>
      {cycles.data.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('calendar.cycles.empty')}</p>
      ) : (
        <ul className="flex flex-col">
          {cycles.data.map((cycle) => {
            const meta = [
              cycle.next_date
                ? t('calendar.cycles.next', { date: formatDate(cycle.next_date) })
                : t('calendar.cycles.never'),
              cycle.owner?.title ?? null,
              cycle.responsible?.name ?? null,
            ].filter(Boolean);
            return (
              <li key={cycle.id}>
                <button
                  type="button"
                  onClick={() => onOpen(cycle.id)}
                  className="flex min-h-touch w-full min-w-0 items-start gap-2.5 rounded-[var(--radius)] px-2 py-2 text-left hover:bg-hover"
                >
                  <Icon className="mt-0.5 size-4 shrink-0 text-accent-ink" aria-hidden="true" />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-sm text-ink-strong">{cycle.title}</span>
                    <span className="text-xs text-ink">{ruleText(t, cycle)}</span>
                    <span className="numeric line-clamp-2 text-xs text-ink-muted">
                      {meta.join(' · ')}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
