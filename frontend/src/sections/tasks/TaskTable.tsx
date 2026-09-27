/**
 * Таблица задач — ноутбук и монитор, рабочее место помощника (ТЗ 6: на телефоне таблиц
 * нет). По умолчанию — порядок сервера, заголовок колонки пересортировывает.
 */

import { ArrowDown, ArrowUp } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { STEP_SIGNAL } from '@/sections/pult/model';
import { deviationText } from '@/sections/pult/text';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Signal } from '@/shared/ui/Signal';

import type { TaskCard } from './model';
import { linkText } from './text';

type SortKey = 'code' | 'title' | 'assignee' | 'due_on';

const COLUMNS: { key: string; sort?: SortKey; align?: 'right' }[] = [
  { key: 'code', sort: 'code' },
  { key: 'title', sort: 'title' },
  { key: 'assignee', sort: 'assignee' },
  { key: 'status' },
  { key: 'attention' },
  { key: 'due', sort: 'due_on' },
  { key: 'checklist', align: 'right' },
];

function valueOf(task: TaskCard, key: SortKey): string {
  if (key === 'assignee') return task.assignee?.name ?? '';
  // Без срока — в конец при сортировке по сроку: срок, которого нет, не ближе остальных.
  if (key === 'due_on') return task.due_on ?? '9999-12-31';
  return task[key];
}

export function TaskTable({ items, onOpen }: { items: TaskCard[]; onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean } | null>(null);

  const rows = useMemo(() => {
    if (!sort) return items;
    const sorted = [...items].sort((left, right) =>
      valueOf(left, sort.key).localeCompare(valueOf(right, sort.key), 'ru'),
    );
    return sort.desc ? sorted.reverse() : sorted;
  }, [items, sort]);

  return (
    <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-line bg-card shadow-card">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line bg-sunken text-xs text-ink-muted">
          <tr>
            {COLUMNS.map((column) => {
              const active = sort !== null && sort.key === column.sort;
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
                        setSort({ key: column.sort!, desc: active ? !sort.desc : false })
                      }
                    >
                      {t(`tasks.table.${column.key}`)}
                      {active ? (
                        sort.desc ? (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        )
                      ) : null}
                    </button>
                  ) : (
                    t(`tasks.table.${column.key}`)
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((task) => (
            <tr key={task.id} className="hover:bg-hover">
              <td className="numeric px-3 py-2 text-xs whitespace-nowrap text-ink-muted">
                {task.code}
              </td>
              <td className="min-w-64 px-3 py-2">
                <button
                  type="button"
                  onClick={() => onOpen(task.id)}
                  className="text-left font-medium text-ink-strong hover:text-accent-ink"
                >
                  {task.title}
                </button>
                <span className="block text-xs text-ink-muted">
                  {[task.type?.name, linkText(t, task)].filter(Boolean).join(' · ')}
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-ink">
                {task.assignee?.name ?? t('tasks.card.noAssignee')}
              </td>
              <td className="px-3 py-2 text-xs text-ink">{t(`tasks.statuses.${task.status}`)}</td>
              <td className="px-3 py-2">
                {task.step ? (
                  <span className="flex flex-col items-start gap-0.5">
                    <Signal state={STEP_SIGNAL[task.step]}>{t(`pult.steps.${task.step}`)}</Signal>
                    <span className="numeric text-xs text-ink-muted">
                      {deviationText(t, { step: task.step, deviation: task.deviation })}
                    </span>
                  </span>
                ) : null}
              </td>
              <td className="numeric px-3 py-2 text-xs whitespace-nowrap text-ink">
                {task.due_on ? formatDate(task.due_on) : t('tasks.card.noDue')}
                {task.moves > 0 ? (
                  <span className="block text-wait-ink">
                    {t('tasks.card.moves', { count: task.moves })}
                  </span>
                ) : null}
              </td>
              <td className="numeric px-3 py-2 text-right text-xs text-ink-muted">
                {task.checklist.total > 0 ? `${task.checklist.done}/${task.checklist.total}` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
