/**
 * «Что если» — перенос срока проекта или вехи без записи в базу (ТЗ 5, план в реальном
 * времени).
 *
 * Расчёт делает сервер тем же кодом, что считает Пульт (`services/metrics.what_if`), и
 * ничего не пишет — поэтому считать может и руководитель. «Применить» записывает новые
 * сроки: это ввод данных, он у помощника, и перенос позже увеличивает счётчик переносов.
 *
 * Результат, посчитанный по старым датам, после правки даты сбрасывается: иначе на экране
 * остался бы ответ на другой вопрос.
 */

import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { LADDER } from '@/sections/pult/model';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Failure } from '@/shared/ui/States';

import type { DatesChange, ProjectDetail, WhatIfChange, WhatIfResult } from './model';
import { stepLabel } from './text';
import { useApplyWhatIf, useWhatIf } from './useProjects';

const PROJECT = 'project';

function initial(project: ProjectDetail): Record<string, string> {
  const draft: Record<string, string> = { [PROJECT]: project.due_on };
  for (const mark of project.milestone_list) if (!mark.is_passed) draft[mark.id] = mark.due_on;
  return draft;
}

export function WhatIf({ project, canApply }: { project: ProjectDetail; canApply: boolean }) {
  const { t } = useTranslation();
  const compute = useWhatIf();
  const apply = useApplyWhatIf();
  const [draft, setDraft] = useState(() => initial(project));
  const [applied, setApplied] = useState(false);
  /**
   * Что посчитано: сроки и версии записей на момент «Посчитать». «Применить» записывает
   * ровно это. Версии с экрана в момент нажатия не годятся: карточка перечитывается каждые
   * 15 секунд, и чужая правка, сделанная между расчётом и применением, прошла бы проверку
   * версии — а расчёт уже показывал бы другую картину (инвариант 15).
   */
  const [basis, setBasis] = useState<DatesChange[] | null>(null);

  const original = initial(project);
  const changes: WhatIfChange[] = Object.entries(draft)
    .filter(([key, value]) => value && value !== original[key])
    .map(([key, value]) => ({
      kind: key === PROJECT ? 'project' : 'milestone',
      id: key === PROJECT ? project.id : key,
      due_on: value,
    }));

  const edit = (key: string, value: string) => {
    setDraft({ ...draft, [key]: value });
    setApplied(false);
    setBasis(null);
    compute.reset();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!changes.length) return;
    const versions = new Map(project.milestone_list.map((mark) => [mark.id, mark.version]));
    setBasis(
      changes.map((change) => ({
        ...change,
        version: change.kind === 'project' ? project.version : (versions.get(change.id) ?? 0),
      })),
    );
    apply.reset();
    compute.mutate({ id: project.id, changes });
  };

  const reset = () => {
    setDraft(original);
    setApplied(false);
    setBasis(null);
    compute.reset();
    apply.reset();
  };

  const open = project.milestone_list.filter((mark) => !mark.is_passed);

  return (
    <section className="rounded-[var(--radius-lg)] border border-line-accent bg-card p-4">
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-ink-strong">{t('projects.whatIf.title')}</h3>
        <p className="text-xs text-ink-muted">{t('projects.whatIf.question')}</p>
      </header>

      <form onSubmit={submit} className="flex flex-col gap-3">
        <DateField
          id={`whatif-${project.id}`}
          label={t('projects.whatIf.projectDue')}
          value={draft[PROJECT] ?? ''}
          changed={draft[PROJECT] !== original[PROJECT]}
          onChange={(value) => edit(PROJECT, value)}
        />
        {open.map((mark) => (
          <DateField
            key={mark.id}
            id={`whatif-${mark.id}`}
            label={mark.title}
            value={draft[mark.id] ?? ''}
            changed={draft[mark.id] !== original[mark.id]}
            onChange={(value) => edit(mark.id, value)}
          />
        ))}

        <div className="flex flex-wrap gap-2">
          <Button type="submit" look="primary" disabled={!changes.length || compute.isPending}>
            {t('projects.whatIf.compute')}
          </Button>
          {canApply && compute.data && basis ? (
            <Button
              type="button"
              disabled={apply.isPending}
              onClick={() =>
                apply.mutate(
                  { id: project.id, changes: basis },
                  {
                    onSuccess: () => {
                      compute.reset();
                      setBasis(null);
                      setApplied(true);
                    },
                  },
                )
              }
            >
              {t('projects.whatIf.apply')}
            </Button>
          ) : null}
          {changes.length || compute.data ? (
            <Button type="button" look="quiet" onClick={reset}>
              {t('projects.whatIf.reset')}
            </Button>
          ) : null}
        </div>
      </form>

      {compute.isError ? <Failure detail={describeError(compute.error)} /> : null}
      {apply.isError ? <Failure detail={describeError(apply.error)} /> : null}
      {compute.data ? <Outcome result={compute.data} /> : null}
      {applied ? (
        <p role="status" className="mt-3 text-sm text-calm-ink">
          {t('projects.whatIf.applied')}
        </p>
      ) : null}
    </section>
  );
}

function DateField({
  id,
  label,
  value,
  changed,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  changed: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
      <label
        htmlFor={id}
        className={cn('min-w-0 text-sm', changed ? 'font-medium text-accent-ink' : 'text-ink')}
      >
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          'numeric min-h-touch rounded-[var(--radius)] border bg-card px-2 text-[15px] text-ink',
          changed ? 'border-line-accent' : 'border-line-strong',
        )}
      />
    </div>
  );
}

/** Ответ расчёта: что станет с проектом, с вехами и с Пультом. Показаны только перемены. */
function Outcome({ result }: { result: WhatIfResult }) {
  const { t } = useTranslation();
  const { before, after } = result.project;
  const marks = result.milestones.filter((mark) => mark.before !== mark.after);
  const pult = LADDER.filter((step) => result.pult.before[step] !== result.pult.after[step]);

  return (
    <div role="status" className="mt-4 flex flex-col gap-3 border-t border-line pt-3 text-sm">
      <div>
        <p className="text-xs text-ink-muted">{t('projects.whatIf.project')}</p>
        <p className="text-ink-strong">
          {before.step === after.step
            ? stepLabel(t, after.step)
            : t('projects.whatIf.stepChange', {
                before: stepLabel(t, before.step),
                after: stepLabel(t, after.step),
              })}
        </p>
        {/* Только то, что меняется: «04.11 → 04.11» заставляет сверять цифры глазами. */}
        {before.due_on !== after.due_on || before.lag_days !== after.lag_days ? (
          <p className="numeric text-xs text-ink">
            {[
              before.due_on !== after.due_on
                ? t('projects.whatIf.dueChange', {
                    before: formatDate(before.due_on),
                    after: formatDate(after.due_on),
                  })
                : null,
              before.lag_days !== after.lag_days
                ? t('projects.whatIf.lagChange', { before: before.lag_days, after: after.lag_days })
                : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        ) : null}
      </div>

      {marks.length ? (
        <ul className="flex flex-col gap-1">
          {marks.map((mark) => (
            <li key={mark.id} className="text-ink">
              <span className="text-ink-muted">{mark.title}: </span>
              {t('projects.whatIf.stepChange', {
                before: stepLabel(t, mark.before),
                after: stepLabel(t, mark.after),
              })}
            </li>
          ))}
        </ul>
      ) : null}

      <div>
        <p className="text-xs text-ink-muted">{t('projects.whatIf.pult')}</p>
        {pult.length ? (
          <ul className="numeric flex flex-col gap-0.5 text-ink">
            {pult.map((step) => (
              <li key={step}>
                {t(`pult.steps.${step}`)}:{' '}
                {t('projects.whatIf.stepChange', {
                  before: result.pult.before[step],
                  after: result.pult.after[step],
                })}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-ink">{t('projects.whatIf.noChange')}</p>
        )}
      </div>

      <p className="text-xs text-ink-muted">{t('projects.whatIf.notSaved')}</p>
    </div>
  );
}
