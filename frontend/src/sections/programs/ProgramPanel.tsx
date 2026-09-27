/**
 * Карточка программы — программа целиком на одном листе.
 *
 * Порядок блоков — порядок вопросов раздела: сколько осталось до даты (отсчёт), успеваем
 * ли к ней, что и когда должно случиться (вехи по годам — свои и подпроектов), из чего
 * программа состоит (подпроекты).
 *
 * Правят программу в карточке проекта (раздел «Проекты»): вехи, «что если», организации.
 * Здесь — чтение и переход туда; второй формы правки у той же записи нет.
 */

import { useTranslation } from 'react-i18next';

import { dueText, lagText } from '@/sections/projects/text';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Block } from '@/shared/ui/Block';
import { Button } from '@/shared/ui/Button';

import { byYear } from './scale';
import { TERMINAL, type ProgramCard, type ProgramMilestone, type ProgramsView } from './model';
import type { PaceAction } from './PaceCard';
import { markShape, stepInk } from './signal';
import { StepMark } from './StepMark';
import { countdownText, markDateText, markLeftText, paceText, readinessText } from './text';

/** Действия карточки: «что если», объём и карточка проекта — всё в «Проектах». */
export type PanelAction = PaceAction | 'card';

interface ProgramPanelProps {
  card: ProgramCard;
  horizon: ProgramsView['horizon'];
  onAction: (id: string, action: PanelAction) => void;
}

export function ProgramPanel({ card, horizon, onAction }: ProgramPanelProps) {
  const { t } = useTranslation();
  const moved = card.original_due_on !== card.due_on;

  // Вехи подпроектов — рядом со своими, с подписью, чьи они: вопрос «что случится в
  // этом году» — про программу целиком, а не про её верхний уровень.
  const marks: (ProgramMilestone & { owner: string | null })[] = [
    ...card.milestones.map((mark) => ({ ...mark, owner: null })),
    ...card.subprojects.flatMap((sub) =>
      sub.milestones.map((mark) => ({ ...mark, owner: sub.title })),
    ),
  ];

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1.5">
        <p className="numeric text-xs text-ink-muted">
          {[card.code, card.type.name, t(`projects.statuses.${card.status}`)].join(' · ')}
        </p>
        <h2 className="text-lg leading-snug font-semibold text-ink-strong">{card.title}</h2>
        <p className="text-sm text-ink">{card.responsible?.name ?? t('programs.panel.noHolder')}</p>
        {card.step ? <StepMark step={card.step} deviation={card.deviation} /> : null}
      </header>

      <Block title={t('programs.panel.countdown')} question={t('programs.panel.countdownQuestion')}>
        {/* У закрытой программы отсчитывать нечего: «дата прошла 280 дн назад» у
            завершённой читалось бы как просрочка. */}
        <p className="numeric text-2xl font-semibold text-ink-strong">
          {TERMINAL.has(card.status)
            ? t(`projects.statuses.${card.status}`)
            : countdownText(t, card.days_left)}
        </p>
        <p className="numeric text-sm text-ink">
          {t('programs.countdown.until', { date: formatDate(card.due_on) })}
          {moved
            ? ` · ${t('programs.countdown.original', { date: formatDate(card.original_due_on) })}`
            : null}
        </p>
        <p className="numeric mt-2 text-xs text-ink-muted">
          {[
            t('programs.panel.started', { date: formatDate(card.started_on) }),
            readinessText(t, card),
            lagText(t, card.lag_days),
          ].join(' · ')}
        </p>
      </Block>

      {card.pace ? (
        <Block title={t('programs.pace.title')} question={t('programs.pace.question')}>
          <p className="text-sm text-ink">{paceText(t, card.pace, card.due_on)}</p>
          {card.pace.verdict === 'behind' ? (
            <span className="mt-2 flex flex-wrap gap-2">
              <Button size="small" onClick={() => onAction(card.id, 'move')}>
                {t('programs.pace.move')}
              </Button>
              <Button size="small" onClick={() => onAction(card.id, 'cut')}>
                {t('programs.pace.cut')}
              </Button>
            </span>
          ) : null}
        </Block>
      ) : null}

      <Block title={t('programs.years.title')} question={t('programs.years.question')}>
        <div className="flex flex-col gap-3">
          {byYear(marks, horizon).map((group) => {
            const passed = group.items.filter((mark) => mark.is_passed).length;
            const title =
              group.bucket === 'before'
                ? t('programs.years.before', { year: horizon.from })
                : group.bucket === 'after'
                  ? t('programs.years.after', { year: horizon.to })
                  : String(group.bucket);
            return (
              <section key={String(group.bucket)} aria-label={title}>
                <h4 className="flex items-baseline gap-2 border-b border-line pb-1">
                  <span className="numeric text-sm font-semibold text-ink-strong">{title}</span>
                  <span className="numeric text-xs text-ink-muted">
                    {group.items.length === 0
                      ? t('programs.years.empty')
                      : t('programs.years.passed', { passed, total: group.items.length })}
                  </span>
                </h4>
                {group.items.length > 0 ? (
                  <ul className="flex flex-col">
                    {group.items.map((mark) => (
                      <li
                        key={mark.id}
                        className="grid grid-cols-[1rem_minmax(0,1fr)_auto] items-baseline gap-x-2 py-1.5"
                      >
                        <span
                          className={cn(
                            'size-2.5 translate-y-0.5 rotate-45 border-2',
                            markShape(mark),
                          )}
                          aria-hidden="true"
                        />
                        <span className="flex min-w-0 flex-col">
                          <span
                            className={cn(
                              'text-sm',
                              mark.is_passed ? 'text-ink-muted' : 'text-ink-strong',
                            )}
                          >
                            {mark.title}
                          </span>
                          <span className="numeric text-xs text-ink-muted">
                            {[
                              markDateText(t, mark),
                              mark.owner
                                ? t('programs.panel.subproject', { title: mark.owner })
                                : null,
                            ]
                              .filter(Boolean)
                              .join(' · ')}
                          </span>
                          {/* Ступень — словом, а не только цветом срока справа: «через 50 дн»
                              у вехи, которая ждёт решения, иначе читается как «всё спокойно». */}
                          {!mark.is_passed && mark.step ? (
                            <span className="mt-1">
                              <StepMark step={mark.step} deviation={mark.deviation} />
                            </span>
                          ) : null}
                        </span>
                        <span
                          className={cn(
                            'numeric text-right text-xs',
                            mark.is_passed ? 'text-ink-muted' : stepInk(mark.step),
                          )}
                        >
                          {markLeftText(t, mark)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>
            );
          })}
        </div>
      </Block>

      <Block
        title={t('programs.panel.subprojects')}
        question={t('programs.panel.subprojectsQuestion')}
        aside={card.subprojects.length > 0 ? String(card.subprojects.length) : undefined}
      >
        {card.subprojects.length === 0 ? (
          <p className="text-sm text-ink-muted">{t('programs.panel.noSubprojects')}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {card.subprojects.map((sub) => (
              <li key={sub.id} className="flex flex-col gap-1 py-2">
                <span className="flex items-baseline gap-2">
                  <span className="min-w-0 flex-1 text-sm font-medium text-ink-strong">
                    {sub.title}
                  </span>
                  <span className="numeric shrink-0 text-xs text-ink-muted">{sub.code}</span>
                </span>
                <span className="numeric text-xs text-ink">
                  {[
                    sub.responsible?.name ?? t('programs.panel.noHolder'),
                    dueText(t, sub),
                    t('programs.panel.readiness', { value: sub.readiness }),
                  ].join(' · ')}
                </span>
                {sub.step ? <StepMark step={sub.step} deviation={sub.deviation} /> : null}
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Button look="plain" onClick={() => onAction(card.id, 'card')}>
        {t('programs.panel.openCard')}
      </Button>
    </div>
  );
}
