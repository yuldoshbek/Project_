/**
 * Решение руководителя в календаре — что решено, кто исполняет, к какому сроку и по чему.
 *
 * Своей карточки у решения нет: лист строится из строки календаря, а кнопка ведёт в
 * карточку того, по чему оно принято, — задачи или проекта (веха — своим проектом). Так
 * касание открывает само решение, как обещал экран, и путь к работе не теряется.
 */

import { useTranslation } from 'react-i18next';

import { StepMark } from '@/sections/programs/StepMark';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';

import type { CalendarItem } from './model';
import { itemTitle } from './text';

interface DecisionPanelProps {
  item: CalendarItem;
  onOpen: (target: { kind: 'project' | 'task'; id: string }) => void;
}

export function DecisionPanel({ item, onOpen }: DecisionPanelProps) {
  const { t } = useTranslation();
  const { kind, id } = item.target;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <p className="text-xs text-ink-muted">
          {item.title && item.decision_kind
            ? `${t('calendar.decision.label')} · ${t(`pult.decisions.${item.decision_kind}`)}`
            : t('calendar.decision.label')}
        </p>
        <h2 className="text-lg leading-snug font-semibold text-ink-strong">{itemTitle(t, item)}</h2>
        {item.step ? <StepMark step={item.step} deviation={item.deviation} /> : null}
      </header>

      <dl className="numeric grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        <dt className="text-ink-muted">{t('calendar.decision.due')}</dt>
        <dd className="text-ink">{formatDate(item.date)}</dd>
        <dt className="text-ink-muted">{t('calendar.decision.responsible')}</dt>
        <dd className="text-ink">{item.responsible?.name ?? t('calendar.decision.nobody')}</dd>
        <dt className="text-ink-muted">{t('calendar.decision.about')}</dt>
        <dd className="text-ink">{item.owner?.title ?? t('calendar.decision.noProject')}</dd>
      </dl>

      {kind === 'task' || kind === 'project' ? (
        <Button className="self-start" onClick={() => onOpen({ kind, id })}>
          {kind === 'task' ? t('calendar.decision.openTask') : t('calendar.decision.openProject')}
        </Button>
      ) : null}
    </div>
  );
}
