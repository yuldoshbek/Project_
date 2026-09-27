/**
 * Новая задача строкой — критерий приёмки раздела (ТЗ 11): создание строкой с разбором
 * срока и ответственного.
 *
 * Человек пишет фразу, как сказал бы вслух; под строкой сразу видно, что понято: тип, срок,
 * ответственный — каждое отдельной подсказкой с тем куском фразы, из которого оно взято.
 * Подсказку можно поправить до «Добавить»: разбор предлагает, решает человек. Поправленная
 * подсказка перестаёт быть подсказкой — её вид меняется, и новый разбор её не трогает
 * (инвариант 6: предложенное системой и внесённое человеком — разные вещи).
 */

import { Sparkles } from 'lucide-react';
import { useEffect, useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';
import { Failure } from '@/shared/ui/States';

import type { ProjectRef, Ref, TaskDetail, TaskType } from './model';
import { projectLabel } from './text';
import { useCreateTask, useParse } from './useTasks';

/** Пауза набора, после которой строка разбирается. Короче — разбор мигает под пальцами. */
const PARSE_DELAY_MS = 250;

type Field = 'type' | 'due' | 'assignee' | 'project';

interface CaptureLineProps {
  types: TaskType[];
  people: Ref[];
  projects: ProjectRef[];
  onCreated: (task: TaskDetail) => void;
  compact: boolean;
}

export function CaptureLine({ types, people, projects, onCreated, compact }: CaptureLineProps) {
  const { t } = useTranslation();
  const ids = useId();
  const parse = useParse();
  const create = useCreateTask();
  const [text, setText] = useState('');
  const [manual, setManual] = useState<Partial<Record<Field, string>>>({});

  useEffect(() => {
    if (!text.trim()) return;
    const timer = window.setTimeout(() => parse.mutate(text), PARSE_DELAY_MS);
    return () => window.clearTimeout(timer);
    // `parse` — новый объект на каждый рендер; зависеть надо от текста.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  // Ответ на устаревший текст не показывается: пока шёл разбор, строку могли дописать.
  const parsed = parse.data && parse.variables === text ? parse.data : null;
  const value = (field: Field, suggested: string | null) =>
    field in manual ? (manual[field] ?? '') : (suggested ?? '');

  const typeCode = value('type', parsed?.type_code ?? null);
  const due = value('due', parsed?.due_on ?? null);
  const assignee = value('assignee', parsed?.assignee_id ?? null);
  const project = value('project', null);
  const title = parsed?.title ?? text.trim();
  const ready = title !== '' && !create.isPending;

  const set = (field: Field, next: string) => setManual({ ...manual, [field]: next });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    create.mutate(
      {
        title,
        type_code: typeCode || null,
        due_on: due || null,
        assignee_id: assignee || null,
        project_id: project || null,
      },
      {
        onSuccess: (task) => {
          setText('');
          setManual({});
          parse.reset();
          onCreated(task);
        },
      },
    );
  };

  /** Подсказка разбора — акцентом; поправленная человеком — обычным полем. */
  const suggested = (field: Field, has: boolean) => has && !(field in manual);
  const chip = (field: Field, has: boolean) =>
    cn(
      'flex min-h-touch min-w-0 items-center gap-1.5 rounded-[var(--radius)] border px-2 text-sm',
      suggested(field, has) ? 'border-line-accent bg-accent-soft/60' : 'border-line bg-card',
    );
  const control = 'min-w-0 flex-1 bg-transparent py-1 text-sm text-ink outline-none';

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-2 rounded-[var(--radius-lg)] border border-line bg-card p-3 shadow-card sm:p-4"
    >
      <label htmlFor={`${ids}-line`} className="text-sm font-semibold text-ink-strong">
        {t('tasks.capture.label')}
      </label>
      <div className="flex gap-2">
        <input
          id={`${ids}-line`}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            if (!event.target.value.trim()) setManual({});
          }}
          placeholder={t('tasks.capture.placeholder')}
          autoComplete="off"
          className="min-h-touch min-w-0 flex-1 rounded-[var(--radius)] border border-line-strong bg-card px-3 text-[15px] text-ink"
        />
        <Button type="submit" look="primary" disabled={!ready}>
          {t('tasks.capture.add')}
        </Button>
      </div>

      {text.trim() ? (
        <div className="flex flex-col gap-2">
          <p className="flex items-center gap-1.5 text-xs text-ink-muted">
            <Sparkles className="size-3.5 text-accent-ink" aria-hidden="true" />
            <span className="min-w-0 truncate">
              {title ? t('tasks.capture.understoodAs', { title }) : t('tasks.capture.understood')}
            </span>
          </p>
          <div className={cn('grid gap-2', compact ? 'grid-cols-1' : 'grid-cols-4')}>
            <label className={chip('type', Boolean(parsed?.type_code))}>
              <span className="shrink-0 text-xs text-ink-muted">{t('tasks.capture.type')}</span>
              <select
                value={typeCode}
                onChange={(event) => set('type', event.target.value)}
                className={control}
              >
                <option value="">{t('tasks.capture.noType')}</option>
                {types.map((type) => (
                  <option key={type.code} value={type.code}>
                    {type.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={chip('due', Boolean(parsed?.due_on))}>
              <span className="shrink-0 text-xs text-ink-muted">{t('tasks.capture.due')}</span>
              <input
                type="date"
                value={due}
                onChange={(event) => set('due', event.target.value)}
                className={cn(control, 'numeric')}
              />
            </label>
            <label className={chip('assignee', Boolean(parsed?.assignee_id))}>
              <span className="shrink-0 text-xs text-ink-muted">{t('tasks.capture.assignee')}</span>
              <select
                value={assignee}
                onChange={(event) => set('assignee', event.target.value)}
                className={control}
              >
                <option value="">{t('tasks.capture.nobody')}</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={chip('project', false)}>
              <span className="shrink-0 text-xs text-ink-muted">{t('tasks.capture.project')}</span>
              <select
                value={project}
                onChange={(event) => set('project', event.target.value)}
                className={control}
              >
                <option value="">{t('tasks.capture.noProject')}</option>
                {projects.map((ref) => (
                  <option key={ref.id} value={ref.id}>
                    {projectLabel(ref)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!compact ? <p className="text-xs text-ink-muted">{t('tasks.capture.hint')}</p> : null}
        </div>
      ) : null}

      {create.isError ? <Failure detail={describeError(create.error)} /> : null}
    </form>
  );
}
