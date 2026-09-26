/**
 * Сведения проекта: название, ответственный, направление, регион, описание (ТЗ 3.1).
 *
 * Их помощник уточняет после заведения: новый проект заводится двумя полями за минуту
 * (ТЗ 7), а направление, регион и описание дописываются, когда они известны. Смотрит и
 * руководитель — без кнопки правки.
 *
 * Направление и регион — из справочников (ТЗ 3.9), а не свободной строкой: по свободной
 * строке не собрать срез по регионам (допущение V7).
 */

import { useQuery } from '@tanstack/react-query';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import type { DictionaryEntry } from '@/shared/api/orbita';
import { dictionariesQuery } from '@/shared/api/queries';
import { Button } from '@/shared/ui/Button';
import { Failure } from '@/shared/ui/States';

import { Block } from './Block';
import type { ProjectDetail } from './model';
import { useProjects, useSaveDetails } from './useProjects';

const FIELD =
  'min-h-touch w-full rounded-[var(--radius)] border border-line-strong bg-card px-2 text-[15px] text-ink';

interface Form {
  title: string;
  responsible: string;
  direction: string;
  region: string;
  description: string;
  version: number;
}

/** Код записи справочника по названию, которое показывает карточка. */
function codeOf(entries: readonly DictionaryEntry[], name: string | null): string {
  return entries.find((entry) => entry.name.ru === name)?.code ?? '';
}

export function DetailsBlock({ project, canEdit }: { project: ProjectDetail; canEdit: boolean }) {
  const { t } = useTranslation();
  const ids = useId();
  const dictionaries = useQuery({ ...dictionariesQuery(), enabled: canEdit });
  const people = useProjects().data?.people ?? [];
  const save = useSaveDetails();
  const [form, setForm] = useState<Form | null>(null);

  const directions = (dictionaries.data?.directions ?? []).filter((entry) => entry.is_active);
  const regions = (dictionaries.data?.regions ?? []).filter((entry) => entry.is_active);

  // Правка начинается с того, что на экране сейчас, и с версией этого момента: карточка
  // перечитывается каждые 15 секунд, и версия в момент «Сохранить» пропустила бы чужую
  // правку (инвариант 15).
  const edit = () => {
    save.reset();
    setForm({
      title: project.title,
      responsible: project.responsible?.id ?? '',
      direction: codeOf(directions, project.direction),
      region: codeOf(regions, project.region),
      description: project.description ?? '',
      version: project.version,
    });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!form || !form.title.trim()) return;
    const nameOf = (entries: DictionaryEntry[], code: string) =>
      entries.find((entry) => entry.code === code)?.name.ru ?? null;
    save.mutate(
      {
        project,
        details: {
          title: form.title,
          responsible_id: form.responsible || null,
          direction_code: form.direction || null,
          region_code: form.region || null,
          description: form.description || null,
          version: form.version,
        },
        names: {
          responsible: people.find((person) => person.id === form.responsible) ?? null,
          direction: nameOf(directions, form.direction),
          region: nameOf(regions, form.region),
        },
      },
      { onSuccess: () => setForm(null) },
    );
  };

  const set = (patch: Partial<Form>) => form && setForm({ ...form, ...patch });
  const id = (name: string) => `${ids}-${name}`;

  if (form) {
    return (
      <Block title={t('projects.details.title')} question={t('projects.details.question')}>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field id={id('title')} label={t('projects.details.name')}>
            <input
              id={id('title')}
              value={form.title}
              required
              onChange={(event) => set({ title: event.target.value })}
              className={FIELD}
            />
          </Field>
          <Field id={id('responsible')} label={t('projects.details.responsible')}>
            <select
              id={id('responsible')}
              value={form.responsible}
              onChange={(event) => set({ responsible: event.target.value })}
              className={FIELD}
            >
              <option value="">{t('projects.details.nobody')}</option>
              {people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id={id('direction')} label={t('projects.details.direction')}>
              <select
                id={id('direction')}
                value={form.direction}
                onChange={(event) => set({ direction: event.target.value })}
                className={FIELD}
              >
                <option value="">{t('projects.details.notSet')}</option>
                {directions.map((entry) => (
                  <option key={entry.code} value={entry.code}>
                    {entry.name.ru}
                  </option>
                ))}
              </select>
            </Field>
            <Field id={id('region')} label={t('projects.details.region')}>
              <select
                id={id('region')}
                value={form.region}
                onChange={(event) => set({ region: event.target.value })}
                className={FIELD}
              >
                <option value="">{t('projects.details.notSet')}</option>
                {regions.map((entry) => (
                  <option key={entry.code} value={entry.code}>
                    {entry.name.ru}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field id={id('description')} label={t('projects.details.description')}>
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
              {t('projects.details.save')}
            </Button>
            <Button type="button" look="quiet" onClick={() => setForm(null)}>
              {t('projects.details.cancel')}
            </Button>
          </div>
          {save.isError ? <Failure detail={describeError(save.error)} /> : null}
          <p className="text-xs text-ink-muted">{t('projects.orgs.draftNote')}</p>
        </form>
      </Block>
    );
  }

  const rows: { label: string; value: string | null }[] = [
    { label: t('projects.details.direction'), value: project.direction },
    { label: t('projects.details.region'), value: project.region },
    { label: t('projects.details.description'), value: project.description },
  ];

  return (
    <Block
      title={t('projects.details.title')}
      question={t('projects.details.question')}
      aside={
        canEdit ? (
          <Button size="small" onClick={edit}>
            {t('projects.details.edit')}
          </Button>
        ) : undefined
      }
    >
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        {rows.map((row) => (
          <div key={row.label} className="contents">
            <dt className="text-ink-muted">{row.label}</dt>
            <dd className={row.value ? 'whitespace-pre-line text-ink' : 'text-ink-muted'}>
              {row.value ?? t('projects.details.notSet')}
            </dd>
          </div>
        ))}
      </dl>
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
