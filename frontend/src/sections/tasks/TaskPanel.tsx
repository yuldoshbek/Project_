/**
 * Карточка задачи — всё о задаче на одном листе.
 *
 * Порядок блоков — порядок вопросов: что с задачей (ступень, вопрос руководителю), куда её
 * двинуть (статус), что осталось сделать (чек-лист), что, кому, к какому сроку и к чему
 * относится (сведения). Вносит и меняет помощник; руководитель смотрит.
 *
 * Статус предлагает только разрешённые переходы — граф на сервере (`domain/tasks`):
 * кнопка, которая кончится отказом, хуже отсутствующей.
 *
 * Отметка пункта чек-листа — самое частое действие с телефона и признак жизни задачи
 * (ТЗ 4): одно касание, без формы.
 */

import { CircleHelp, X } from 'lucide-react';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { STEP_SIGNAL } from '@/sections/pult/model';
import { deviationText } from '@/sections/pult/text';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Block } from '@/shared/ui/Block';
import { Button } from '@/shared/ui/Button';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import type { ProjectRef, Ref, TaskDetail, TaskType } from './model';
import { dueText, originText, projectLabel } from './text';
import { useChecklist, useEditTask, useTask, useTaskStatus } from './useTasks';

interface TaskPanelProps {
  id: string;
  canEdit: boolean;
  types: TaskType[];
  people: Ref[];
  projects: ProjectRef[];
}

export function TaskPanel({ id, ...rest }: TaskPanelProps) {
  const task = useTask(id);
  if (task.isPending) return <Loading />;
  if (task.isError) {
    return <Failure detail={describeError(task.error)} onRetry={() => void task.refetch()} />;
  }
  return <Panel task={task.data} {...rest} />;
}

function Panel({
  task,
  canEdit,
  types,
  people,
  projects,
}: Omit<TaskPanelProps, 'id'> & { task: TaskDetail }) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-2">
        <p className="numeric text-xs text-ink-muted">
          {[task.code, originText(t, task), task.type?.name, t(`tasks.statuses.${task.status}`)]
            .filter(Boolean)
            .join(' · ')}
        </p>
        <h2 className="text-xl leading-snug font-semibold text-ink-strong">{task.title}</h2>
        {task.step ? (
          <div className="flex flex-wrap items-center gap-2">
            <Signal state={STEP_SIGNAL[task.step]}>{t(`pult.steps.${task.step}`)}</Signal>
            <span className="numeric text-sm text-ink">
              {deviationText(t, { step: task.step, deviation: task.deviation })}
            </span>
          </div>
        ) : null}
      </header>

      {task.question ? (
        <div className="flex gap-2 rounded-[var(--radius)] bg-call-soft p-3 text-call-ink">
          <CircleHelp className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div className="min-w-0 text-sm">
            <p className="font-medium">{t('tasks.panel.question')}</p>
            <p>{task.question.text}</p>
            <p className="numeric text-xs">{formatDate(task.question.asked_on)}</p>
          </div>
        </div>
      ) : null}

      {canEdit ? <StatusControl task={task} /> : null}

      <Checklist task={task} canEdit={canEdit} />

      <Details task={task} canEdit={canEdit} types={types} people={people} projects={projects} />
    </div>
  );
}

function StatusControl({ task }: { task: TaskDetail }) {
  const { t } = useTranslation();
  const change = useTaskStatus();
  return (
    <Block title={t('tasks.panel.status')}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex min-h-touch items-center rounded-[var(--radius)] bg-accent px-3 text-sm font-medium text-ink-inverse md:min-h-9">
          {t(`tasks.statuses.${task.status}`)}
        </span>
        {task.transitions.map((status) => (
          <Button
            key={status}
            size="small"
            disabled={change.isPending}
            onClick={() => change.mutate({ id: task.id, status, version: task.version })}
          >
            {t(`tasks.statuses.${status}`)}
          </Button>
        ))}
      </div>
      {change.isError ? (
        <div className="mt-3">
          <Failure detail={describeError(change.error)} />
        </div>
      ) : null}
    </Block>
  );
}

function Checklist({ task, canEdit }: { task: TaskDetail; canEdit: boolean }) {
  const { t } = useTranslation();
  const ids = useId();
  const checklist = useChecklist();
  const [text, setText] = useState('');

  const add = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    checklist.mutate({ kind: 'add', id: task.id, text }, { onSuccess: () => setText('') });
  };

  return (
    <Block
      title={t('tasks.panel.checklist')}
      question={t('tasks.panel.checklistQuestion')}
      aside={task.checklist.total > 0 ? t('tasks.card.checklist', task.checklist) : undefined}
    >
      {task.checklist_items.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('tasks.panel.noItems')}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line">
          {task.checklist_items.map((item) => (
            <li key={item.id} className="flex items-center gap-2">
              <label className="flex min-h-touch min-w-0 flex-1 cursor-pointer items-center gap-3 py-1">
                <input
                  type="checkbox"
                  checked={item.is_done}
                  disabled={!canEdit || checklist.isPending}
                  onChange={(event) =>
                    checklist.mutate({
                      kind: 'toggle',
                      id: task.id,
                      itemId: item.id,
                      done: event.target.checked,
                      version: item.version,
                    })
                  }
                  className="size-5 shrink-0 accent-[var(--accent)]"
                />
                <span
                  className={cn(
                    'min-w-0 text-sm',
                    item.is_done ? 'text-ink-muted line-through' : 'text-ink',
                  )}
                >
                  {item.text}
                </span>
              </label>
              {canEdit ? (
                <Button
                  look="quiet"
                  size="icon"
                  disabled={checklist.isPending}
                  aria-label={t('tasks.panel.removeItem', { text: item.text })}
                  onClick={() =>
                    checklist.mutate({
                      kind: 'remove',
                      id: task.id,
                      itemId: item.id,
                      version: item.version,
                    })
                  }
                >
                  <X className="size-4" aria-hidden="true" />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        <form onSubmit={add} className="mt-2 flex gap-2">
          <label htmlFor={`${ids}-item`} className="sr-only">
            {t('tasks.panel.itemLabel')}
          </label>
          <input
            id={`${ids}-item`}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={t('tasks.panel.itemPlaceholder')}
            className="min-h-touch min-w-0 flex-1 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-[15px] text-ink"
          />
          <Button type="submit" disabled={!text.trim() || checklist.isPending}>
            {t('tasks.panel.addItem')}
          </Button>
        </form>
      ) : null}
      {checklist.isError ? (
        <div className="mt-2">
          <Failure detail={describeError(checklist.error)} />
        </div>
      ) : null}
    </Block>
  );
}

interface Form {
  title: string;
  type: string;
  assignee: string;
  due: string;
  project: string;
  description: string;
  version: number;
}

function Details({
  task,
  canEdit,
  types,
  people,
  projects,
}: {
  task: TaskDetail;
  canEdit: boolean;
  types: TaskType[];
  people: Ref[];
  projects: ProjectRef[];
}) {
  const { t } = useTranslation();
  const ids = useId();
  const save = useEditTask();
  const [form, setForm] = useState<Form | null>(null);

  // Правка начинается с того, что на экране сейчас, и с версией этого момента (инвариант 15).
  const edit = () => {
    save.reset();
    setForm({
      title: task.title,
      type: task.type?.code ?? '',
      assignee: task.assignee?.id ?? '',
      due: task.due_on ?? '',
      project: task.project?.id ?? '',
      description: task.description ?? '',
      version: task.version,
    });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!form || !form.title.trim()) return;
    save.mutate(
      {
        id: task.id,
        edit: {
          title: form.title,
          type_code: form.type || null,
          due_on: form.due || null,
          assignee_id: form.assignee || null,
          project_id: form.project || null,
          description: form.description || null,
          version: form.version,
        },
      },
      { onSuccess: () => setForm(null) },
    );
  };

  const set = (patch: Partial<Form>) => form && setForm({ ...form, ...patch });
  const field =
    'min-h-touch w-full rounded-[var(--radius)] border border-line-strong bg-card px-2 text-[15px] text-ink';
  const id = (name: string) => `${ids}-${name}`;

  if (form) {
    return (
      <Block title={t('tasks.panel.details')} question={t('tasks.panel.detailsQuestion')}>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field id={id('title')} label={t('tasks.panel.name')}>
            <input
              id={id('title')}
              value={form.title}
              required
              onChange={(event) => set({ title: event.target.value })}
              className={field}
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id={id('type')} label={t('tasks.panel.type')}>
              <select
                id={id('type')}
                value={form.type}
                onChange={(event) => set({ type: event.target.value })}
                className={field}
              >
                <option value="">{t('tasks.capture.noType')}</option>
                {types.map((type) => (
                  <option key={type.code} value={type.code}>
                    {type.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field id={id('assignee')} label={t('tasks.panel.assignee')}>
              <select
                id={id('assignee')}
                value={form.assignee}
                onChange={(event) => set({ assignee: event.target.value })}
                className={field}
              >
                <option value="">{t('tasks.capture.nobody')}</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field id={id('due')} label={t('tasks.panel.due')}>
              <input
                id={id('due')}
                type="date"
                value={form.due}
                onChange={(event) => set({ due: event.target.value })}
                className={cn(field, 'numeric')}
              />
            </Field>
            <Field id={id('project')} label={t('tasks.panel.project')}>
              <select
                id={id('project')}
                value={form.project}
                onChange={(event) => set({ project: event.target.value })}
                className={field}
              >
                <option value="">{t('tasks.capture.noProject')}</option>
                {projects.map((ref) => (
                  <option key={ref.id} value={ref.id}>
                    {projectLabel(ref)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field id={id('description')} label={t('tasks.panel.description')}>
            <textarea
              id={id('description')}
              value={form.description}
              rows={3}
              onChange={(event) => set({ description: event.target.value })}
              className="w-full rounded-[var(--radius)] border border-line-strong bg-card p-2 text-[15px] text-ink"
            />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" look="primary" disabled={save.isPending || !form.title.trim()}>
              {t('tasks.panel.save')}
            </Button>
            <Button type="button" look="quiet" onClick={() => setForm(null)}>
              {t('tasks.panel.cancel')}
            </Button>
          </div>
          {save.isError ? <Failure detail={describeError(save.error)} /> : null}
        </form>
      </Block>
    );
  }

  const link = task.project
    ? projectLabel(task.project)
    : task.ijro
      ? t('tasks.card.ijro', { label: task.ijro.label })
      : null;
  const rows: { label: string; value: string | null; hint?: string | undefined }[] = [
    {
      label: t('tasks.panel.due'),
      value: dueText(t, task),
      hint: task.moves > 0 ? t('tasks.card.moves', { count: task.moves }) : undefined,
    },
    { label: t('tasks.panel.assignee'), value: task.assignee?.name ?? null },
    // Привязка — проект или поручение; без привязки — обычное дело (ТЗ 3.2), так и пишем.
    { label: t('tasks.panel.link'), value: link ?? t('tasks.panel.noLink') },
    { label: t('tasks.panel.description'), value: task.description },
  ];

  return (
    <Block
      title={t('tasks.panel.details')}
      question={t('tasks.panel.detailsQuestion')}
      aside={
        canEdit ? (
          <Button size="small" onClick={edit}>
            {t('tasks.panel.edit')}
          </Button>
        ) : undefined
      }
    >
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        {rows.map((row) => (
          <div key={row.label} className="contents">
            <dt className="text-ink-muted">{row.label}</dt>
            <dd className={row.value ? 'whitespace-pre-line text-ink' : 'text-ink-muted'}>
              {row.value ?? t('tasks.panel.notSet')}
              {row.hint ? <span className="block text-xs text-wait-ink">{row.hint}</span> : null}
            </dd>
          </div>
        ))}
      </dl>
      <p className="numeric mt-2 text-xs text-ink-muted">
        {t('tasks.panel.created', { date: formatDate(task.created_on) })}
      </p>
    </Block>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-sm text-ink">
        {label}
      </label>
      {children}
    </div>
  );
}
