/**
 * Что понято из фразы — тип, срок, ответственный — отдельными полями; проект — выбором.
 *
 * Подсказка разбора выделена акцентом; поправленная человеком выглядит обычным полем. Общие
 * для строки «Новая задача» и Захвата: у Захвата полей меньше — у письма один срок ответа.
 */

import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';

import type { ProjectRef, Ref, TaskType } from './model';
import { projectLabel } from './text';
import type { LineParse, ParsedField } from './useLineParse';

interface ParsedFieldsProps {
  line: LineParse;
  fields: readonly ParsedField[];
  types: TaskType[];
  people: Ref[];
  projects: ProjectRef[];
  /**
   * Раскладка: `stack` — столбиком (телефон), `pairs` — по два (узкий лист), `row` — все в
   * ряд (строка «Новая задача» во всю ширину раздела).
   */
  layout: 'stack' | 'pairs' | 'row';
  /** Подпись поля вместо обычной: у письма срок — «срок ответа», у мероприятия — «дата». */
  labels?: Partial<Record<ParsedField, string>>;
}

export function ParsedFields({
  line,
  fields,
  types,
  people,
  projects,
  layout,
  labels = {},
}: ParsedFieldsProps) {
  const { t } = useTranslation();

  const chip = (field: ParsedField) =>
    cn(
      'flex min-h-touch min-w-0 items-center gap-1.5 rounded-[var(--radius)] border px-2 text-sm',
      line.suggested(field) ? 'border-line-accent bg-accent-soft/60' : 'border-line bg-card',
    );
  const control = 'min-w-0 flex-1 bg-transparent py-1 text-sm text-ink outline-none';
  const label = (field: ParsedField) => labels[field] ?? t(`tasks.capture.${field}`);
  const columns =
    layout === 'stack' || fields.length === 1
      ? 'grid-cols-1'
      : layout === 'pairs' || fields.length === 2
        ? 'grid-cols-2'
        : 'grid-cols-4';

  return (
    <div className={cn('grid gap-2', columns)}>
      {fields.map((field) => (
        <label key={field} className={chip(field)}>
          <span className="shrink-0 text-xs text-ink-muted">{label(field)}</span>
          {field === 'due' ? (
            <input
              type="date"
              value={line.value('due')}
              onChange={(event) => line.set('due', event.target.value)}
              className={cn(control, 'numeric')}
            />
          ) : (
            <select
              value={line.value(field)}
              onChange={(event) => line.set(field, event.target.value)}
              className={control}
            >
              {field === 'type' ? (
                <>
                  <option value="">{t('tasks.capture.noType')}</option>
                  {types.map((type) => (
                    <option key={type.code} value={type.code}>
                      {type.name}
                    </option>
                  ))}
                </>
              ) : field === 'assignee' ? (
                <>
                  <option value="">{t('tasks.capture.nobody')}</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name}
                    </option>
                  ))}
                </>
              ) : (
                <>
                  <option value="">{t('tasks.capture.noProject')}</option>
                  {projects.map((ref) => (
                    <option key={ref.id} value={ref.id}>
                      {projectLabel(ref)}
                    </option>
                  ))}
                </>
              )}
            </select>
          )}
        </label>
      ))}
    </div>
  );
}
