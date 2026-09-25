/**
 * Новый проект — меньше минуты (ТЗ 3.1, «стоимость ввода»).
 *
 * Обязательны два поля: название и тип. Остальное подставлено: начало — сегодня, срок и
 * вехи — из шаблона типа, ответственного можно назначить позже. Вехи шаблона видны до
 * сохранения, чтобы помощник знал, что появится в карточке, а не узнал потом.
 */

import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Failure } from '@/shared/ui/States';

import type { ProjectCard, ProjectDetail, ProjectType, Ref } from './model';
import { useCreateProject } from './useProjects';

const DAY_MS = 86_400_000;

function addDays(day: string, days: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

const FIELD =
  'min-h-touch w-full rounded-[var(--radius)] border border-line-strong bg-card px-2 text-[15px] text-ink';

interface CreateProjectProps {
  today: string;
  types: ProjectType[];
  people: Ref[];
  programs: ProjectCard[];
  onCreated: (project: ProjectDetail) => void;
  onCancel: () => void;
}

export function CreateProject({
  today,
  types,
  people,
  programs,
  onCreated,
  onCancel,
}: CreateProjectProps) {
  const { t } = useTranslation();
  const create = useCreateProject();
  const ids = useId();
  const [title, setTitle] = useState('');
  const [typeCode, setTypeCode] = useState('');
  const [started, setStarted] = useState(today);
  const [due, setDue] = useState('');
  const [responsible, setResponsible] = useState('');
  const [parent, setParent] = useState('');
  const [multiyear, setMultiyear] = useState(false);

  const type = types.find((each) => each.code === typeCode);
  const ready = title.trim() !== '' && type !== undefined && started !== '';

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    create.mutate(
      {
        title: title.trim(),
        type_code: typeCode,
        started_on: started,
        due_on: due || null,
        responsible_id: responsible || null,
        parent_id: parent || null,
        is_multiyear: multiyear,
      },
      { onSuccess: onCreated },
    );
  };

  const id = (name: string) => `${ids}-${name}`;

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <header>
        <h2 className="text-xl font-semibold text-ink-strong">{t('projects.form.title')}</h2>
        <p className="mt-1 text-sm text-ink-muted">{t('projects.form.hint')}</p>
      </header>

      <Field id={id('title')} label={t('projects.form.name')} required>
        <input
          id={id('title')}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          autoFocus
          required
          className={FIELD}
        />
      </Field>

      <Field id={id('type')} label={t('projects.form.type')} required>
        <select
          id={id('type')}
          value={typeCode}
          onChange={(event) => setTypeCode(event.target.value)}
          required
          className={FIELD}
        >
          <option value="">{t('projects.form.chooseType')}</option>
          {types.map((each) => (
            <option key={each.code} value={each.code}>
              {each.name}
            </option>
          ))}
        </select>
      </Field>

      {type ? (
        <section className="rounded-[var(--radius)] border border-line bg-sunken p-3">
          <h3 className="text-xs font-medium text-ink-muted">{t('projects.form.template')}</h3>
          <ol className="mt-1 flex flex-col gap-0.5 text-sm text-ink">
            {type.template.map((step) => (
              <li key={step.title} className="flex justify-between gap-3">
                <span className="min-w-0">{step.title}</span>
                <span className="numeric shrink-0 text-ink-muted">
                  {formatDate(addDays(started || today, step.offset_days))}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        <Field id={id('started')} label={t('projects.form.started')}>
          <input
            id={id('started')}
            type="date"
            value={started}
            onChange={(event) => setStarted(event.target.value)}
            className={`numeric ${FIELD}`}
          />
        </Field>
        <Field id={id('due')} label={t('projects.form.due')}>
          <input
            id={id('due')}
            type="date"
            value={due}
            min={started}
            onChange={(event) => setDue(event.target.value)}
            className={`numeric ${FIELD}`}
          />
        </Field>
      </div>

      <Field id={id('responsible')} label={t('projects.form.responsible')}>
        <select
          id={id('responsible')}
          value={responsible}
          onChange={(event) => setResponsible(event.target.value)}
          className={FIELD}
        >
          <option value="">{t('projects.form.nobody')}</option>
          {people.map((person) => (
            <option key={person.id} value={person.id}>
              {person.name}
            </option>
          ))}
        </select>
      </Field>

      {programs.length ? (
        <Field id={id('parent')} label={t('projects.form.parent')}>
          <select
            id={id('parent')}
            value={parent}
            onChange={(event) => {
              setParent(event.target.value);
              if (event.target.value) setMultiyear(false);
            }}
            className={FIELD}
          >
            <option value="">{t('projects.form.noParent')}</option>
            {programs.map((program) => (
              <option key={program.id} value={program.id}>
                {program.title}
              </option>
            ))}
          </select>
        </Field>
      ) : null}

      {!parent ? (
        <label className="flex min-h-touch items-center gap-3 text-sm text-ink">
          <input
            type="checkbox"
            checked={multiyear}
            onChange={(event) => setMultiyear(event.target.checked)}
            className="size-5 accent-[var(--accent)]"
          />
          {t('projects.form.multiyear')}
        </label>
      ) : null}

      {create.isError ? <Failure detail={describeError(create.error)} /> : null}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" look="primary" disabled={!ready || create.isPending}>
          {t('projects.form.submit')}
        </Button>
        <Button type="button" look="quiet" onClick={onCancel}>
          {t('projects.panel.cancel')}
        </Button>
      </div>
    </form>
  );
}

function Field({
  id,
  label,
  required = false,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-sm text-ink">
        {label}
        {required ? <span className="text-burn-ink">{t('projects.form.required')}</span> : null}
      </label>
      {children}
    </div>
  );
}
