/**
 * Вкладка «Вопросы»: четыре вопроса раздела (ТЗ 5).
 *
 * У каждого — вопрос в заголовке, ответ числом или фразой, дата данных и действие
 * (инвариант 3). Пустой ответ — слова, а не ноль, и действия у него нет. Скорость ответа —
 * только у организаций с пятью письмами и больше; про остальные сказано словами (ТЗ 4).
 */

import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';

import type { Filter } from './filter';
import type { Tab } from './InteractionSection';
import type { InteractionView, QuestionAnswer } from './model';
import { answerText, orgName } from './text';

interface QuestionsTabProps {
  view: InteractionView;
  device: Device;
  freshness: string;
  onLetters: (filter: Partial<Filter>) => void;
  onOrganization: (id: string) => void;
  onTab: (tab: Tab) => void;
}

export function QuestionsTab({
  view,
  device,
  freshness,
  onLetters,
  onOrganization,
  onTab,
}: QuestionsTabProps) {
  const { t } = useTranslation();

  const act = (answer: QuestionAnswer) => {
    if (answer.key === 'speed') onTab('organizations');
    else if (answer.key === 'sleeping') onTab('agreements');
    else onLetters({ question: answer.key });
  };

  return (
    <div
      className={cn(
        'grid gap-3',
        device === 'phone' ? 'grid-cols-1' : 'grid-cols-2 gap-4',
        device === 'monitor' && 'grid-cols-4 gap-5',
      )}
    >
      {view.questions.map((answer) => {
        const text = answerText(t, answer);
        return (
          <Card
            key={answer.key}
            title={t(`interaction.questions.${answer.key}.title`)}
            freshness={freshness}
            className="flex flex-col"
          >
            <p className="numeric text-lg leading-snug font-semibold text-ink-strong">
              {text.main}
            </p>
            {text.detail ? <p className="mt-1 text-sm text-ink-muted">{text.detail}</p> : null}
            <Breakdown answer={answer} onLetters={onLetters} onOrganization={onOrganization} />
            {text.empty ? null : (
              <div className="mt-auto pt-3">
                <Button size="small" onClick={() => act(answer)}>
                  {t(`interaction.questions.${answer.key}.action`)}
                </Button>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

const LINE = 'flex min-h-touch w-full items-center justify-between gap-3 text-left text-sm';

/** «Кому напомнить» и «кто медленнее» — каждая строка ведёт к своим письмам или карточке. */
function Breakdown({
  answer,
  onLetters,
  onOrganization,
}: {
  answer: QuestionAnswer;
  onLetters: (filter: Partial<Filter>) => void;
  onOrganization: (id: string) => void;
}) {
  const { t } = useTranslation();

  if (answer.key === 'not_answering' && answer.organizations.length > 0) {
    return (
      <ul className="mt-2 divide-y divide-line border-t border-line">
        {answer.organizations.slice(0, 3).map((each) => (
          <li key={each.organization.id}>
            <button
              type="button"
              className={LINE}
              onClick={() =>
                onLetters({ question: 'not_answering', organization: each.organization.id })
              }
            >
              <span className="min-w-0 truncate text-ink">{orgName(each.organization)}</span>
              <span className="numeric shrink-0 text-xs text-wait-ink">
                {t('interaction.questions.not_answering.org', {
                  count: each.count,
                  days: each.oldest_days,
                })}
              </span>
            </button>
          </li>
        ))}
      </ul>
    );
  }

  if (answer.key === 'speed' && answer.measured.length > 0) {
    return (
      <ul className="mt-2 divide-y divide-line border-t border-line">
        {answer.measured.slice(0, 3).map((each) => (
          <li key={each.organization.id}>
            <button
              type="button"
              className={LINE}
              onClick={() => onOrganization(each.organization.id)}
            >
              <span className="min-w-0 truncate text-ink">{orgName(each.organization)}</span>
              <span className="numeric shrink-0 text-xs text-ink-muted">
                {t('interaction.questions.speed.org', {
                  days: each.median_days,
                  count: each.letters,
                })}
              </span>
            </button>
          </li>
        ))}
      </ul>
    );
  }

  return null;
}
