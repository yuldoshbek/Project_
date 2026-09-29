/**
 * Обход — еженедельная очередь того, где данные могли отстать от жизни (ТЗ 7, CONTEXT).
 *
 * У каждого пункта причина «почему вы здесь» и два-три действия в одно касание. Кнопки
 * «всё нормально» нет: пункт уходит, когда данные поправлены, — иначе обход превращается
 * в прокликивание, и отставшие данные остаются отставшими. На телефоне это мини-обход
 * (ТЗ 6): те же пункты, действия под пальцем столбиком.
 *
 * Название открывает раздел, где живёт запись: там её можно поправить подробнее.
 */

import { Link } from '@tanstack/react-router';
import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { sectionPath } from '@/app/sections';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Failure } from '@/shared/ui/States';

import { NEEDS_INPUT, type Person, type Round, type RoundAction, type RoundItem } from './model';
import { useRoundAction } from './useManagement';

/** Что сделано и с чем — подпись говорит, что именно произошло, а не общее «сделано». */
interface Notice {
  action: RoundAction;
  title: string;
}

interface RowProps {
  item: RoundItem;
  people: Person[];
  compact: boolean;
  onDone: (notice: Notice) => void;
}

function RoundRow({ item, people, compact, onDone }: RowProps) {
  const { t } = useTranslation();
  const ids = useId();
  const act = useRoundAction();
  const [asking, setAsking] = useState<RoundAction | null>(null);
  const [value, setValue] = useState('');

  const run = (action: RoundAction, input?: string) =>
    act.mutate(
      { id: item.id, action, ...(input === undefined ? {} : { input }) },
      { onSuccess: () => onDone({ action, title: item.title }) },
    );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (asking && value.trim()) run(asking, value.trim());
  };

  const meta = [item.owner, item.responsible ?? t('management.round.noResponsible')].filter(
    Boolean,
  );

  return (
    <li className="flex flex-col gap-2 rounded-[var(--radius)] border border-line bg-card p-3">
      <span className="text-xs text-ink-muted">{t(`management.round.kinds.${item.reason}`)}</span>
      <Link
        to={sectionPath(item.target.kind === 'project' ? 'projects' : 'tasks')}
        // Цель нажатия — не меньше 44 px и у ссылки: на телефоне название — тоже кнопка.
        className="flex min-h-touch items-center text-[15px] leading-snug font-medium text-ink-strong hover:underline"
      >
        {item.title}
      </Link>
      <span className="truncate text-xs text-ink-muted">{meta.join(' · ')}</span>
      <p className="text-sm text-ink">
        {t(`management.round.reasons.${item.reason}`, { days: item.days })}
      </p>

      {asking ? (
        <form onSubmit={submit} className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-xs text-ink-muted" htmlFor={`${ids}-input`}>
            {t(`management.round.input.${asking}`)}
          </label>
          {asking === 'assign' ? (
            <select
              id={`${ids}-input`}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className="min-h-touch rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink"
            >
              <option value="">{t('management.round.input.pick')}</option>
              {people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={`${ids}-input`}
              // Строку открыли касанием ради ввода: курсор сразу в поле.
              autoFocus
              value={value}
              onChange={(event) => setValue(event.target.value)}
              maxLength={500}
              className="min-h-touch rounded-[var(--radius)] border border-line-strong bg-card px-3 text-sm text-ink"
            />
          )}
          <span className="flex flex-wrap gap-2">
            <Button
              type="submit"
              look="primary"
              size="small"
              disabled={!value.trim() || act.isPending}
            >
              {t('management.round.input.save')}
            </Button>
            <Button
              type="button"
              size="small"
              onClick={() => {
                setAsking(null);
                setValue('');
                act.reset();
              }}
            >
              {t('management.round.input.cancel')}
            </Button>
          </span>
        </form>
      ) : (
        <span className={cn('flex gap-2', compact ? 'flex-col' : 'flex-wrap')}>
          {item.actions.map((action, index) => (
            <Button
              key={action}
              look={index === 0 ? 'primary' : 'plain'}
              size="small"
              disabled={act.isPending}
              onClick={() => (NEEDS_INPUT.has(action) ? setAsking(action) : run(action))}
            >
              {t(`management.round.actions.${action}`)}
            </Button>
          ))}
        </span>
      )}

      {act.isError ? <Failure detail={describeError(act.error)} /> : null}
    </li>
  );
}

export function RoundTab({
  round,
  people,
  compact,
}: {
  round: Round;
  people: Person[];
  compact: boolean;
}) {
  const { t } = useTranslation();
  const [notice, setNotice] = useState<Notice | null>(null);
  const left = round.items.length;

  return (
    <Card title={t('management.round.title')} question={t('management.round.question')}>
      <p className="numeric mb-1 flex flex-wrap gap-x-3 text-sm text-ink">
        <span className="font-semibold text-ink-strong">
          {t('management.round.left', { count: left })}
        </span>
        <span>{t('management.round.done', { count: round.done })}</span>
        <span className="text-ink-muted">
          {t('management.round.week', {
            from: formatDate(round.week_from),
            to: formatDate(round.week_to),
          })}
        </span>
      </p>
      <p className="mb-3 text-xs text-ink-muted">{t('management.round.hint')}</p>

      {notice ? (
        <p
          role="status"
          className="mb-3 rounded-[var(--radius)] bg-calm-soft px-3 py-2 text-sm text-calm-ink"
        >
          {t(`management.round.notice.${notice.action}`, { title: notice.title })}
        </p>
      ) : null}

      {left === 0 ? (
        <p className="text-sm text-ink-muted">{t('management.round.empty')}</p>
      ) : (
        <ul className={cn('grid gap-3', compact ? 'grid-cols-1' : 'grid-cols-2 2xl:grid-cols-3')}>
          {round.items.map((item) => (
            <RoundRow
              key={item.id}
              item={item}
              people={people}
              compact={compact}
              onDone={setNotice}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}
