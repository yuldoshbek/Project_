/**
 * Новый годовой цикл — вносит помощник (ТЗ 3.1, 7: обязательных полей минимум).
 *
 * Обязательно одно название; правило по умолчанию — «ежегодно». Даты на год вперёд видны
 * до записи: помощник сразу видит, что заводит. Если дат за год нет, форма называет
 * причину: у цикла «раз в три года» — ближайшую дату за горизонтом, у 30 февраля — что
 * такого дня нет ни в одном году; такой цикл не записывается.
 *
 * Числа хранятся строкой, пока их набирают: стёртое поле остаётся пустым, а не
 * подменяется единицей — иначе «20» → стереть → «5» давало 15.
 */

import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Failure } from '@/shared/ui/States';

import type { CycleDetail, CycleRule, CycleRuleFields, Ref } from './model';
import { monthNames } from './text';
import { useCreateCycle, useCyclePreview } from './useCalendar';

const RULES: readonly CycleRule[] = ['annual', 'quarterly', 'every_n_years'];

/** Пределы чисел — те же, что у базы (`repos/models/cycles.py`): раз в 2–10 лет. */
const DAY = { min: 1, max: 31 } as const;
const EVERY = { min: 2, max: 10 } as const;
/** Год начала — в десять лет от текущего в обе стороны: дальше это уже опечатка. */
const ANCHOR_SPAN = 10;

interface CycleFormProps {
  year: number;
  people: Ref[];
  projects: { id: string; title: string }[];
  onCancel: () => void;
  onCreated: (cycle: CycleDetail) => void;
}

/** Целое в пределах — или `null`, пока поле пустое или число вне пределов. */
function whole(text: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(text.trim())) return null;
  const value = Number(text);
  return value >= min && value <= max ? value : null;
}

export function CycleForm({ year, people, projects, onCancel, onCreated }: CycleFormProps) {
  const { t } = useTranslation();
  const id = useId();
  const create = useCreateCycle();
  const [title, setTitle] = useState('');
  const [rule, setRule] = useState<CycleRule>('annual');
  const [month, setMonth] = useState(1);
  const [dayText, setDayText] = useState('20');
  const [everyText, setEveryText] = useState('3');
  const [anchorText, setAnchorText] = useState(String(year));
  const [projectId, setProjectId] = useState<string | null>(null);
  const [responsibleId, setResponsibleId] = useState<string | null>(null);

  const anchorLimits = { min: year - ANCHOR_SPAN, max: year + ANCHOR_SPAN };
  const day = whole(dayText, DAY.min, DAY.max);
  const everyYears = rule === 'every_n_years' ? whole(everyText, EVERY.min, EVERY.max) : 1;
  const anchorYear =
    rule === 'every_n_years' ? whole(anchorText, anchorLimits.min, anchorLimits.max) : year;
  const fields: CycleRuleFields | null =
    day !== null && everyYears !== null && anchorYear !== null
      ? { rule, month, day, every_years: everyYears, anchor_year: anchorYear }
      : null;
  const preview = useCyclePreview(fields);
  const never = fields !== null && preview.data?.next_date === null && !preview.isPlaceholderData;
  const ready = title.trim() !== '' && fields !== null && !never;

  const field =
    'min-h-touch w-full rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';
  const invalid = 'border-burn';

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready || fields === null) return;
    create.mutate(
      { ...fields, title, project_id: projectId, responsible_id: responsibleId },
      { onSuccess: onCreated },
    );
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <h2 className="text-lg font-semibold text-ink-strong">{t('calendar.form.title')}</h2>

      <label className="flex flex-col gap-1 text-sm text-ink">
        {t('calendar.form.name')}
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={t('calendar.form.namePlaceholder')}
          maxLength={300}
          required
          className={field}
        />
      </label>

      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-sm text-ink">{t('calendar.form.rule')}</legend>
        <span className="flex flex-wrap gap-2">
          {RULES.map((each) => (
            <label
              key={each}
              className={cn(
                'inline-flex min-h-touch cursor-pointer items-center rounded-[var(--radius-pill)] border px-3 text-sm',
                // Сам переключатель спрятан, и обводка фокуса на нём не видна: её рисует
                // подпись — с клавиатуры ноутбука видно, где стоишь (ТЗ 9).
                'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent',
                rule === each
                  ? 'border-line-accent bg-accent-soft text-accent-ink'
                  : 'border-line bg-card text-ink',
              )}
            >
              <input
                type="radio"
                name={`${id}-rule`}
                value={each}
                checked={rule === each}
                onChange={() => setRule(each)}
                className="sr-only"
              />
              {t(`calendar.form.rules.${each}`)}
            </label>
          ))}
        </span>
        {rule === 'quarterly' ? (
          <span className="text-xs text-ink-muted">{t('calendar.form.quarterlyHint')}</span>
        ) : null}
      </fieldset>

      <div className="grid grid-cols-2 gap-3">
        {rule !== 'quarterly' ? (
          <label className="flex flex-col gap-1 text-sm text-ink">
            {t('calendar.form.month')}
            <select
              value={month}
              onChange={(event) => setMonth(Number(event.target.value))}
              className={field}
            >
              {monthNames().map((name, index) => (
                <option key={name} value={index + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <NumberField
          label={t('calendar.form.day')}
          value={dayText}
          onChange={setDayText}
          error={day === null ? t('calendar.form.errors.day') : null}
          className={cn(field, day === null && invalid)}
        />
        {rule === 'every_n_years' ? (
          <>
            <NumberField
              label={t('calendar.form.every')}
              value={everyText}
              onChange={setEveryText}
              error={everyYears === null ? t('calendar.form.errors.every') : null}
              className={cn(field, everyYears === null && invalid)}
            />
            <NumberField
              label={t('calendar.form.anchor')}
              value={anchorText}
              onChange={setAnchorText}
              error={
                anchorYear === null
                  ? t('calendar.form.errors.anchor', {
                      from: anchorLimits.min,
                      to: anchorLimits.max,
                    })
                  : null
              }
              className={cn(field, anchorYear === null && invalid)}
            />
          </>
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t('calendar.form.project')}
          <select
            value={projectId ?? ''}
            onChange={(event) => setProjectId(event.target.value || null)}
            className={field}
          >
            <option value="">{t('calendar.form.noProject')}</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.title}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t('calendar.form.responsible')}
          <select
            value={responsibleId ?? ''}
            onChange={(event) => setResponsibleId(event.target.value || null)}
            className={field}
          >
            <option value="">{t('calendar.form.nobody')}</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Пока считаются даты нового правила, видны прежние — приглушёнными; приговор
          «дат нет» прежнего правила к новому не относится и не показывается. */}
      <section
        aria-label={t('calendar.form.preview')}
        aria-busy={preview.isPlaceholderData}
        className="flex flex-col gap-1"
      >
        <h3 className="text-sm font-medium text-ink">{t('calendar.form.preview')}</h3>
        {fields === null || !preview.data ? null : preview.data.dates.length > 0 ? (
          <p
            className={cn(
              'numeric text-sm text-ink-muted',
              preview.isPlaceholderData && 'opacity-60',
            )}
          >
            {preview.data.dates.map((date) => formatDate(date)).join(' · ')}
          </p>
        ) : preview.isPlaceholderData ? null : preview.data.next_date ? (
          <p className="numeric text-sm text-ink-muted">
            {t('calendar.form.previewLater', { date: formatDate(preview.data.next_date) })}
          </p>
        ) : (
          <p className="text-sm text-wait-ink">{t('calendar.form.previewNever')}</p>
        )}
      </section>

      {create.isError ? (
        <Failure detail={describeError(create.error)} onRetry={() => create.reset()} />
      ) : null}

      <span className="flex flex-wrap gap-2">
        <Button type="submit" look="primary" disabled={create.isPending || !ready}>
          {t('calendar.form.save')}
        </Button>
        <Button type="button" onClick={onCancel}>
          {t('calendar.form.cancel')}
        </Button>
      </span>
    </form>
  );
}

function NumberField({
  label,
  value,
  onChange,
  error,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error: string | null;
  className: string;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label className="flex flex-col gap-1 text-sm text-ink">
        {label}
        <input
          // Не `type="number"`: оно молча отбрасывает набранное не числом и спорит с
          // проверкой, а цифровую клавиатуру iPhone даёт `inputMode`.
          inputMode="numeric"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={error !== null}
          aria-describedby={error ? id : undefined}
          className={cn(className, 'numeric')}
        />
      </label>
      {error ? (
        <span id={id} className="text-xs text-burn-ink">
          {error}
        </span>
      ) : null}
    </div>
  );
}
