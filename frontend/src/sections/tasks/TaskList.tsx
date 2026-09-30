/**
 * Список задач по сроку — ответ на «к какому сроку» (вопрос раздела).
 *
 * Группы идут в порядке срочности: просрочено, сегодня, завтра, ближайшая неделя, позже,
 * без срока. Группу считает сервер (`horizon`), порядок внутри — тоже: экран только
 * раскладывает. Готовые и отменённые свёрнуты: они отвечают на другой вопрос — «что
 * сделали», — и в списке дел их место в конце и по требованию.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';

import { HORIZONS, type Horizon, type TaskCard } from './model';
import { TaskRow } from './TaskRow';

/** Цвет заголовка группы: просрочено и сегодня — тревога, остальное спокойно. */
const HEADING: Partial<Record<Horizon, string>> = {
  overdue: 'text-burn-ink',
  today: 'text-burn-ink',
  tomorrow: 'text-wait-ink',
};

interface TaskListProps {
  items: TaskCard[];
  onOpen: (id: string) => void;
  selected?: string | null;
}

export function TaskList({ items, onOpen, selected = null }: TaskListProps) {
  const { t } = useTranslation();
  const [showClosed, setShowClosed] = useState(false);
  const closed = items.filter((task) => task.horizon === 'closed');

  return (
    <div className="flex flex-col gap-4">
      {HORIZONS.filter((horizon) => horizon !== 'closed').map((horizon) => {
        const group = items.filter((task) => task.horizon === horizon);
        if (group.length === 0) return null;
        return (
          <section key={horizon} aria-label={t(`tasks.horizons.${horizon}`)}>
            <h2
              className={cn(
                'mb-2 flex items-baseline gap-2 text-sm font-semibold',
                HEADING[horizon] ?? 'text-ink-strong',
              )}
            >
              {t(`tasks.horizons.${horizon}`)}
              <span className="numeric text-xs font-normal text-ink-muted">{group.length}</span>
            </h2>
            <ul className="flex flex-col gap-2">
              {group.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  onOpen={onOpen}
                  selected={selected === task.id}
                />
              ))}
            </ul>
          </section>
        );
      })}

      {closed.length > 0 ? (
        <section aria-label={t('tasks.horizons.closed')}>
          <Button look="quiet" size="small" onClick={() => setShowClosed(!showClosed)}>
            {showClosed ? t('tasks.hideClosed') : t('tasks.showClosed', { count: closed.length })}
          </Button>
          {showClosed ? (
            <ul className="mt-2 flex flex-col gap-2">
              {closed.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  onOpen={onOpen}
                  selected={selected === task.id}
                />
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
