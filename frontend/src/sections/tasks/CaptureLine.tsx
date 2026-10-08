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
import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { Button } from '@/shared/ui/Button';
import { Failure } from '@/shared/ui/States';

import type { ProjectRef, Ref, TaskDetail, TaskType } from './model';
import { ParsedFields } from './ParsedFields';
import { useLineParse } from './useLineParse';
import { useCreateTask } from './useTasks';

const FIELDS = ['type', 'due', 'assignee', 'project'] as const;

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
  const create = useCreateTask();
  const [text, setText] = useState('');
  const line = useLineParse(text);
  const title = line.title;
  const ready = title !== '' && !create.isPending;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    create.mutate(
      {
        title,
        type_code: line.value('type') || null,
        due_on: line.value('due') || null,
        assignee_id: line.value('assignee') || null,
        project_id: line.value('project') || null,
      },
      {
        onSuccess: (task) => {
          setText('');
          line.reset();
          onCreated(task);
        },
      },
    );
  };

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
            if (!event.target.value.trim()) line.clearManual();
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
          <ParsedFields
            line={line}
            fields={FIELDS}
            types={types}
            people={people}
            projects={projects}
            layout={compact ? 'stack' : 'row'}
          />
          {!compact ? <p className="text-xs text-ink-muted">{t('tasks.capture.hint')}</p> : null}
        </div>
      ) : null}

      {create.isError ? <Failure detail={describeError(create.error)} /> : null}
    </form>
  );
}
