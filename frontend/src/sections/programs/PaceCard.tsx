/**
 * «Успеваем ли к дате программы?» — вопрос раздела (ТЗ 5): фраза с правилом; урезать
 * объём или перенести.
 *
 * Ответ — одной строкой сверху: сколько программ не успевает. Ниже — не успевающие с
 * фразой и двумя действиями, затем те, по которым прогноза нет, и коротко — успевающие.
 * Правило счёта написано под списком: «не успеваем» без правила спорит с готовностью в
 * процентах, и не верят обоим.
 */

import { useTranslation } from 'react-i18next';

import { formatDateTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';

import type { Pace, ProgramCard } from './model';
import { paceShort, paceText } from './text';

/** Что предлагает строка «не успеваем»: перенести дату или урезать объём (ТЗ 5). */
export type PaceAction = 'move' | 'cut';

const ORDER = { behind: 0, little_data: 1, on_track: 2 } as const;

interface PaceCardProps {
  items: ProgramCard[];
  asOf: string;
  onOpen: (id: string) => void;
  onAction: (id: string, action: PaceAction) => void;
}

export function PaceCard({ items, asOf, onOpen, onAction }: PaceCardProps) {
  const { t } = useTranslation();
  const rated = items
    .filter((card): card is ProgramCard & { pace: Pace } => card.pace !== null)
    .sort((left, right) => ORDER[left.pace.verdict] - ORDER[right.pace.verdict]);
  const behind = rated.filter((card) => card.pace.verdict === 'behind').length;
  const known = rated.filter((card) => card.pace.verdict !== 'little_data').length;
  const rule = rated[0]?.pace;

  const unknown = rated.length - known;

  // Знаменатель — программы с прогнозом: «1 из 5» при одной без прогноза читалось бы как
  // «четыре успевают», то есть незнание — как благополучие (ТЗ 5).
  const verdict =
    behind > 0
      ? t('programs.pace.answerBehind', { count: behind, total: known })
      : known > 0
        ? t('programs.pace.answerAll', { total: known })
        : null;
  const answer = [
    verdict,
    unknown > 0
      ? t(verdict ? 'programs.pace.answerUnknown' : 'programs.pace.answerLittle', {
          count: unknown,
        })
      : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <Card
      title={t('programs.pace.title')}
      question={t('programs.pace.question')}
      freshness={t('pult.asOf', { when: formatDateTime(asOf) })}
    >
      {rated.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('programs.pace.none')}</p>
      ) : (
        <>
          <p
            className={
              behind > 0
                ? 'mb-3 text-sm font-semibold text-burn-ink'
                : 'mb-3 text-sm font-semibold text-ink-strong'
            }
          >
            {answer}
          </p>
          <ul className="flex flex-col gap-3">
            {rated.map((card) => (
              <li key={card.id} className="flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={() => onOpen(card.id)}
                  className="flex min-h-touch min-w-0 items-center gap-2 text-left hover:text-accent-ink md:min-h-9"
                >
                  <span className="min-w-0 flex-1 text-sm font-medium text-ink-strong">
                    {card.title}
                  </span>
                  {card.pace.verdict === 'on_track' ? (
                    <span className="numeric shrink-0 text-xs text-calm-ink">
                      {paceShort(t, card.pace)}
                    </span>
                  ) : null}
                </button>
                {card.pace.verdict !== 'on_track' ? (
                  <p
                    className={
                      card.pace.verdict === 'behind' ? 'text-sm text-ink' : 'text-sm text-ink-muted'
                    }
                  >
                    {paceText(t, card.pace, card.due_on)}
                  </p>
                ) : null}
                {card.pace.verdict === 'behind' ? (
                  <span className="flex flex-wrap gap-2">
                    <Button size="small" onClick={() => onAction(card.id, 'move')}>
                      {t('programs.pace.move')}
                    </Button>
                    <Button size="small" onClick={() => onAction(card.id, 'cut')}>
                      {t('programs.pace.cut')}
                    </Button>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          {rule ? (
            <p className="mt-4 text-xs text-ink-muted">
              {t('programs.pace.rule', { window: rule.window_days, min: rule.min_closed_tasks })}
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}
