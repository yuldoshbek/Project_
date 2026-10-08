/**
 * «Кто перегружен?» — вопрос раздела по ТЗ 5: просрочки по ответственным.
 *
 * Ответ — строка на человека: сколько просрочено, сколько горит, сколько всего в работе.
 * Действие — касание: список оставляет задачи этого человека (ТЗ 5: у показателя есть
 * действие). Считает сервер по тем же ступеням, что стоят в строках списка, — число у
 * человека обязано совпадать с числом его строк.
 */

import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { formatDateTime } from '@/shared/time';
import { Card } from '@/shared/ui/Card';

import type { LoadRow } from './model';

interface LoadCardProps {
  load: LoadRow[];
  asOf: string;
  active: string | null;
  onPick: (personId: string) => void;
}

export function LoadCard({ load, asOf, active, onPick }: LoadCardProps) {
  const { t } = useTranslation();
  const widest = Math.max(1, ...load.map((row) => row.open));

  return (
    <Card
      title={t('tasks.load.title')}
      question={t('tasks.load.question')}
      freshness={t('pult.asOf', { when: formatDateTime(asOf) })}
    >
      {load.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('tasks.load.none')}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {load.map((row) => {
            const pressed = active === row.person.id;
            return (
              <li key={row.person.id}>
                <button
                  type="button"
                  aria-pressed={pressed}
                  aria-label={t('tasks.load.filter', { name: row.person.name })}
                  onClick={() => onPick(row.person.id)}
                  className={cn(
                    'flex min-h-touch w-full flex-col gap-1 rounded-[var(--radius)] px-2 py-1.5 text-left',
                    'transition-colors duration-[var(--motion-fast)] hover:bg-hover',
                    pressed && 'bg-accent-soft',
                  )}
                >
                  <span className="flex w-full items-baseline gap-2">
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink-strong">
                      {row.person.name}
                    </span>
                    <span className="numeric shrink-0 text-xs text-ink-muted">
                      {[
                        row.overdue > 0 ? t('tasks.load.overdue', { count: row.overdue }) : null,
                        row.burning > 0 ? t('tasks.load.burning', { count: row.burning }) : null,
                        t('tasks.load.open', { count: row.open }),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </span>
                  {/* Полоса — доля просроченного и горящего в работе человека; длина — объём
                      его работы относительно самого загруженного. */}
                  <span
                    className="flex h-1.5 overflow-hidden rounded-[var(--radius-pill)] bg-sunken"
                    style={{ width: `${Math.max(12, (row.open / widest) * 100)}%` }}
                    aria-hidden="true"
                  >
                    <span
                      className="bg-burn"
                      style={{ width: `${(row.overdue / row.open) * 100}%` }}
                    />
                    <span
                      className="bg-wait"
                      style={{ width: `${(row.burning / row.open) * 100}%` }}
                    />
                    <span className="flex-1 bg-accent/40" />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
