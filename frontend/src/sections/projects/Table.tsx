/**
 * Таблица проектов — ноутбук и монитор (ТЗ 6: на телефоне таблиц нет).
 *
 * По умолчанию строки идут в порядке сервера — сначала то, что требует внимания. Заголовок
 * колонки пересортировывает; повторное нажатие меняет направление.
 */

import { ArrowDown, ArrowUp } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { STEP_SIGNAL } from '@/sections/pult/model';
import { deviationText } from '@/sections/pult/text';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Signal } from '@/shared/ui/Signal';

import type { ProjectCard } from './model';

type SortKey = 'code' | 'title' | 'due_on' | 'readiness' | 'lag_days';

const COLUMNS: { key: string; sort?: SortKey; align?: 'right' }[] = [
  { key: 'code', sort: 'code' },
  { key: 'title', sort: 'title' },
  { key: 'responsible' },
  { key: 'status' },
  { key: 'attention' },
  { key: 'due', sort: 'due_on' },
  { key: 'readiness', sort: 'readiness', align: 'right' },
  { key: 'lag', sort: 'lag_days', align: 'right' },
  { key: 'impediment' },
];

export function Table({ items, onOpen }: { items: ProjectCard[]; onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean } | null>(null);

  const rows = useMemo(() => {
    if (!sort) return items;
    const sorted = [...items].sort((left, right) => {
      const a = left[sort.key];
      const b = right[sort.key];
      return typeof a === 'number' && typeof b === 'number'
        ? a - b
        : String(a).localeCompare(String(b), 'ru');
    });
    return sort.desc ? sorted.reverse() : sorted;
  }, [items, sort]);

  return (
    <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-line bg-card shadow-card">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line bg-sunken text-xs text-ink-muted">
          <tr>
            {COLUMNS.map((column) => {
              const active = sort && sort.key === column.sort;
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={active ? (sort.desc ? 'descending' : 'ascending') : undefined}
                  className={cn('px-3 py-2 font-medium', column.align === 'right' && 'text-right')}
                >
                  {column.sort ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-ink"
                      onClick={() =>
                        setSort(
                          active
                            ? { key: column.sort!, desc: !sort.desc }
                            : { key: column.sort!, desc: false },
                        )
                      }
                    >
                      {t(`projects.table.${column.key}`)}
                      {active ? (
                        sort.desc ? (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        )
                      ) : null}
                    </button>
                  ) : (
                    t(`projects.table.${column.key}`)
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((card) => (
            <tr key={card.id} className="hover:bg-hover">
              <td className="numeric px-3 py-2 text-xs whitespace-nowrap text-ink-muted">
                {card.code}
              </td>
              <td className="min-w-56 px-3 py-2">
                <button
                  type="button"
                  onClick={() => onOpen(card.id)}
                  className="text-left font-medium text-ink-strong hover:text-accent-ink"
                >
                  {card.title}
                </button>
                <span className="block text-xs text-ink-muted">
                  {card.parent
                    ? `${card.type.name} · ${t('projects.card.parent', { title: card.parent.title })}`
                    : card.type.name}
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-ink">
                {card.responsible?.name ?? t('projects.card.noHolder')}
              </td>
              <td className="px-3 py-2 text-xs text-ink">
                {t(`projects.statuses.${card.status}`)}
              </td>
              <td className="px-3 py-2">
                {card.step ? (
                  <span className="flex flex-col items-start gap-0.5">
                    <Signal state={STEP_SIGNAL[card.step]}>{t(`pult.steps.${card.step}`)}</Signal>
                    <span className="numeric text-xs text-ink-muted">
                      {deviationText(t, { step: card.step, deviation: card.deviation })}
                    </span>
                  </span>
                ) : null}
              </td>
              <td className="numeric px-3 py-2 text-xs whitespace-nowrap text-ink">
                {formatDate(card.due_on)}
                {card.moves > 0 ? (
                  <span className="block text-wait-ink">
                    {t('projects.card.moves', { count: card.moves })}
                  </span>
                ) : null}
              </td>
              <td className="numeric px-3 py-2 text-right text-xs text-ink">
                {t('projects.table.percent', { value: card.readiness })}
              </td>
              <td
                className={cn(
                  'numeric px-3 py-2 text-right text-xs',
                  card.lag_days > 0 ? 'text-wait-ink' : 'text-ink-muted',
                )}
              >
                {card.lag_days}
              </td>
              <td className="max-w-[240px] px-3 py-2 text-xs text-ink">
                {card.impediment ? (
                  <>
                    <span className="line-clamp-2">{card.impediment.text}</span>
                    <span className="numeric text-ink-muted">
                      {formatDate(card.impediment.updated_on)}
                    </span>
                  </>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
