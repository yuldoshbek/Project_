/**
 * Вкладка «Вопросы»: двенадцать вопросов раздела (ТЗ 5, V31).
 *
 * У каждого — вопрос в заголовке, ответ числом или фразой, дата таблицы и действие
 * (инвариант 3). Пустой ответ — слова, а не ноль, и действия у него нет: открывать нечего.
 * Порядок — `QUESTIONS`: сначала то, что руководитель решает с телефона (критерий 3
 * блока 2).
 */

import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';

import type { Filter } from './filter';
import type { Tab } from './IjroSection';
import type { IjroView, QuestionAnswer } from './model';
import { answerText } from './text';

interface QuestionsTabProps {
  view: IjroView;
  device: Device;
  viewer: Role;
  freshness: string;
  onList: (filter: Partial<Filter>) => void;
  onTab: (tab: Tab) => void;
  onSpravka: () => void;
}

export function QuestionsTab({
  view,
  device,
  viewer,
  freshness,
  onList,
  onTab,
  onSpravka,
}: QuestionsTabProps) {
  const { t } = useTranslation();

  const act = (answer: QuestionAnswer) => {
    if (answer.key === 'documents') onTab('documents');
    else if (answer.key === 'report_up') onSpravka();
    // Подтверждать продления — дело помощника; руководитель смотрит, что изменилось.
    else if (answer.key === 'last_batch' && viewer === 'assistant') onTab('upload');
    else onList({ question: answer.key });
  };

  return (
    <div
      className={cn(
        'grid gap-3',
        device === 'phone'
          ? 'grid-cols-1'
          : device === 'monitor'
            ? 'grid-cols-4 gap-5'
            : 'grid-cols-3 gap-4',
      )}
    >
      {view.questions.map((answer) => {
        const text = answerText(t, answer);
        const action =
          answer.key === 'last_batch' && viewer === 'leader'
            ? t('ijro.questions.last_batch.actionLeader')
            : t(`ijro.questions.${answer.key}.action`);
        return (
          <Card
            key={answer.key}
            title={t(`ijro.questions.${answer.key}.title`)}
            freshness={freshness}
            className="flex flex-col"
          >
            <p className="numeric text-lg leading-snug font-semibold text-ink-strong">
              {text.main}
            </p>
            {text.detail ? <p className="mt-1 text-sm text-ink-muted">{text.detail}</p> : null}
            <Breakdown answer={answer} onList={onList} />
            {text.empty ? null : (
              <div className="mt-auto pt-3">
                <Button size="small" onClick={() => act(answer)}>
                  {action}
                </Button>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

/** «Кого поторопить» и «по ведомствам» — разбивка ответа, каждая строка — свой список. */
function Breakdown({
  answer,
  onList,
}: {
  answer: QuestionAnswer;
  onList: (filter: Partial<Filter>) => void;
}) {
  const { t } = useTranslation();
  const line = 'flex min-h-touch w-full items-center justify-between gap-3 text-left text-sm';

  if (answer.key === 'burning' && answer.by_person.length > 0) {
    return (
      <ul className="mt-2 divide-y divide-line border-t border-line">
        {answer.by_person.slice(0, 3).map((each) => {
          const key = each.person?.id ?? `raw:${each.responsible_raw}`;
          return (
            <li key={key}>
              <button
                type="button"
                className={line}
                onClick={() => onList({ question: 'burning', person: key })}
              >
                <span className="min-w-0 truncate text-ink">
                  {each.person?.name ?? each.responsible_raw}
                </span>
                <span className="numeric shrink-0 text-xs text-burn-ink">
                  {[
                    each.overdue > 0
                      ? t('ijro.questions.burning.personOverdue', { count: each.overdue })
                      : null,
                    each.burning > 0
                      ? t('ijro.questions.burning.personBurning', { count: each.burning })
                      : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    );
  }

  if (answer.key === 'foreign' && answer.organizations.length > 0) {
    return (
      <ul className="mt-2 divide-y divide-line border-t border-line">
        {answer.organizations.slice(0, 3).map((each) => (
          <li key={each.organization.id}>
            <button
              type="button"
              className={line}
              onClick={() => onList({ question: 'foreign', organization: each.organization.id })}
            >
              <span className="min-w-0 truncate text-ink">
                {each.organization.short_name ?? each.organization.name}
              </span>
              <span className="numeric shrink-0 text-xs text-wait-ink">{each.count}</span>
            </button>
          </li>
        ))}
      </ul>
    );
  }

  return null;
}
