/**
 * «Что должно случиться до конца года?» — вопрос раздела (ТЗ 5): список вех с отсчётом.
 *
 * Вехи программ и их подпроектов со сроком до 31 декабря, по месяцам. Просроченная веха
 * стоит первой: она не случилась и всё ещё должна случиться в этом году. Действие —
 * касание: открывается программа, к которой относится веха.
 */

import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { formatDateTime } from '@/shared/time';
import { Card } from '@/shared/ui/Card';

import type { YearEndRow } from './model';
import { stepInk } from './signal';
import { StepMark } from './StepMark';
import { markLeftText, metaText, monthTitle } from './text';

interface YearEndCardProps {
  rows: YearEndRow[];
  year: number;
  asOf: string;
  onOpen: (programId: string) => void;
}

export function YearEndCard({ rows, year, asOf, onOpen }: YearEndCardProps) {
  const { t } = useTranslation();
  // «Просрочено» — одно правило для числа и для группы: срок прошёл. По ступени нельзя: у
  // просроченной вехи с вопросом руководителю ступень «ждёт решения», и число разошлось бы
  // со строками группы под ним.
  const overdue = rows.filter((row) => row.milestone.days_left < 0).length;
  const burning = rows.filter((row) => row.milestone.step === 'burning').length;

  const groups: { key: string; title: string; rows: YearEndRow[] }[] = [];
  for (const row of rows) {
    const late = row.milestone.days_left < 0;
    const key = late ? 'overdue' : row.milestone.due_on.slice(0, 7);
    let group = groups.find((each) => each.key === key);
    if (!group) {
      group = {
        key,
        title: late ? t('programs.yearEnd.overdue') : monthTitle(row.milestone.due_on),
        rows: [],
      };
      groups.push(group);
    }
    group.rows.push(row);
  }

  return (
    <Card
      title={t('programs.yearEnd.title', { year })}
      question={t('programs.yearEnd.question')}
      freshness={t('pult.asOf', { when: formatDateTime(asOf) })}
    >
      {rows.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('programs.yearEnd.none')}</p>
      ) : (
        <>
          <p className="numeric mb-3 text-sm text-ink">
            {[
              t('programs.yearEnd.answer', { count: rows.length }),
              overdue > 0 ? t('programs.yearEnd.overdueCount', { count: overdue }) : null,
              burning > 0 ? t('programs.yearEnd.burningCount', { count: burning }) : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
          <div className="flex flex-col gap-3">
            {groups.map((group) => (
              <section key={group.key} aria-label={group.title}>
                <h3
                  className={cn(
                    'mb-1 text-xs font-semibold tracking-wide uppercase',
                    group.key === 'overdue' ? 'text-burn-ink' : 'text-ink-muted',
                  )}
                >
                  {group.title}
                </h3>
                <ul className="flex flex-col">
                  {group.rows.map((row) => (
                    <li key={row.milestone.id}>
                      {/* Один столбец при любой ширине: карточка узкая и на телефоне, и в
                          колонке монитора, а рядом с отсчётом обрезались бы ответственный и
                          программа — то, ради чего строку читают. */}
                      <button
                        type="button"
                        onClick={() => onOpen(row.program.id)}
                        className="flex min-h-touch w-full min-w-0 flex-col gap-0.5 rounded-[var(--radius)] px-2 py-1.5 text-left hover:bg-hover"
                      >
                        <span className="numeric text-xs">
                          <span className={cn('font-medium', stepInk(row.milestone.step))}>
                            {markLeftText(t, row.milestone)}
                          </span>
                          <span className="text-ink">{metaText(t, row)}</span>
                        </span>
                        <span className="text-sm text-ink-strong">{row.milestone.title}</span>
                        {/* Чья веха: подпроект и программа — по касанию откроется программа. */}
                        <span className="line-clamp-2 text-xs text-ink-muted">
                          {row.subproject
                            ? t('programs.yearEnd.inSubproject', {
                                subproject: row.subproject.title,
                                program: row.program.title,
                              })
                            : row.program.title}
                        </span>
                        {row.milestone.step === 'awaiting_decision' ? (
                          <StepMark step={row.milestone.step} deviation={row.milestone.deviation} />
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
