/**
 * Справочники — «из чего выбирают в формах?» (ТЗ 3.9: редактируются помощником, не кодом).
 *
 * Значение переименовывают, ставят выше или ниже (порядок — порядок в формах), выключают и
 * добавляют. Выключенное исчезает из форм, но у старых записей остаётся своим: удалять
 * значение, на которое ссылаются, нельзя. Рядом — сколько записей на него ссылается: это
 * ответ на вопрос «можно ли выключить без последствий». У типа проекта — шаблон вех: что
 * подставится в новый проект этого типа.
 *
 * Набор статусов задан правилами переходов, регионов — ТЗ 3.1: статус переименовывают и
 * переставляют, но не добавляют и не выключают; регион — всё, кроме «добавить». Названия
 * правятся по-русски; узбекские письменности приходят с языками в блоке 3 (V22).
 *
 * Правка идёт с версией, которую видел человек (инвариант 15). Строки не пересоздаются от
 * версии: иначе отказ «значение уже изменили» исчезал бы вместе с черновиком.
 */

import { ArrowDown, ArrowUp, ChevronLeft, Pencil, Trash2 } from 'lucide-react';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Failure } from '@/shared/ui/States';

import type {
  DictionaryEntry,
  DictionaryGroup,
  DictionaryKind,
  OrganizationKind,
  TemplateStep,
} from './model';
import { useDictionaryChange, useStepChange } from './useManagement';

const ORG_KINDS: readonly OrganizationKind[] = [
  'ministry',
  'agency',
  'khokimiyat',
  'international',
  'company',
];

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-3 text-sm text-ink';

function EntryRow({
  kind,
  entry,
  group,
  index,
  canEdit,
  opened,
  onTemplate,
  template,
}: {
  kind: DictionaryKind;
  entry: DictionaryEntry;
  group: DictionaryGroup;
  index: number;
  canEdit: boolean;
  opened: boolean;
  onTemplate: (() => void) | null;
  /** Шаблон вех раскрытого типа — под его строкой, а не под всем списком. */
  template: ReactNode;
}) {
  const { t } = useTranslation();
  const change = useDictionaryChange();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(entry.name);
  const [orgKind, setOrgKind] = useState<OrganizationKind | undefined>(entry.org_kind);

  // Правку открывают с тем, что сейчас на сервере, а не с прошлым черновиком.
  const edit = () => {
    setName(entry.name);
    setOrgKind(entry.org_kind);
    change.reset();
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    change.reset();
  };

  const meta = [
    entry.org_kind ? t(`projects.orgs.kinds.${entry.org_kind}`) : null,
    entry.is_center ? t('management.dictionaries.center') : null,
    t('management.dictionaries.used', { count: entry.used }),
    entry.is_active ? null : t('management.dictionaries.inactive'),
  ].filter(Boolean);

  const rename = (event: FormEvent) => {
    event.preventDefault();
    change.mutate(
      {
        op: 'rename',
        kind,
        id: entry.id,
        name,
        version: entry.version,
        ...(kind === 'organizations' && orgKind ? { orgKind } : {}),
      },
      { onSuccess: () => setEditing(false) },
    );
  };

  return (
    <li
      className={cn(
        'flex flex-col gap-2 rounded-[var(--radius)] border px-3 py-2',
        opened ? 'border-line-accent bg-accent-soft/40' : 'border-line bg-card',
      )}
    >
      {editing ? (
        <form onSubmit={rename} className="flex flex-wrap items-center gap-2">
          <input
            aria-label={t('management.dictionaries.name')}
            // Правку открыли касанием ради ввода: курсор сразу в поле.
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={200}
            className={cn(FIELD, 'flex-1 basis-48')}
          />
          {kind === 'organizations' ? (
            <select
              aria-label={t('management.dictionaries.orgKindOf', { name: entry.name })}
              value={orgKind ?? 'ministry'}
              onChange={(event) => setOrgKind(event.target.value as OrganizationKind)}
              className={FIELD}
            >
              {ORG_KINDS.map((each) => (
                <option key={each} value={each}>
                  {t(`projects.orgs.kinds.${each}`)}
                </option>
              ))}
            </select>
          ) : null}
          <Button
            type="submit"
            look="primary"
            size="small"
            disabled={!name.trim() || change.isPending}
          >
            {t('management.dictionaries.save')}
          </Button>
          <Button type="button" size="small" onClick={cancel}>
            {t('management.dictionaries.cancel')}
          </Button>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="flex min-w-0 flex-1 basis-48 flex-col">
            <span
              className={cn(
                'text-sm font-medium',
                entry.is_active ? 'text-ink-strong' : 'text-ink-muted line-through',
              )}
            >
              {entry.name}
            </span>
            <span className="numeric text-xs text-ink-muted">{meta.join(' · ')}</span>
          </span>
          {canEdit ? (
            <span className="flex flex-wrap items-center gap-1">
              <Button
                look="quiet"
                size="icon"
                aria-label={t('management.dictionaries.up', { name: entry.name })}
                disabled={index === 0 || change.isPending}
                onClick={() =>
                  change.mutate({
                    op: 'move',
                    kind,
                    id: entry.id,
                    step: -1,
                    version: entry.version,
                  })
                }
              >
                <ArrowUp className="size-4" aria-hidden="true" />
              </Button>
              <Button
                look="quiet"
                size="icon"
                aria-label={t('management.dictionaries.down', { name: entry.name })}
                disabled={index === group.entries.length - 1 || change.isPending}
                onClick={() =>
                  change.mutate({ op: 'move', kind, id: entry.id, step: 1, version: entry.version })
                }
              >
                <ArrowDown className="size-4" aria-hidden="true" />
              </Button>
              <Button
                look="quiet"
                size="icon"
                aria-label={t('management.dictionaries.rename', { name: entry.name })}
                onClick={edit}
              >
                <Pencil className="size-4" aria-hidden="true" />
              </Button>
              {group.can_disable ? (
                <Button
                  size="small"
                  disabled={change.isPending}
                  onClick={() =>
                    change.mutate({ op: 'toggle', kind, id: entry.id, version: entry.version })
                  }
                >
                  {entry.is_active
                    ? t('management.dictionaries.disable')
                    : t('management.dictionaries.enable')}
                </Button>
              ) : null}
            </span>
          ) : null}
          {onTemplate ? (
            <Button size="small" look={opened ? 'primary' : 'plain'} onClick={onTemplate}>
              {t('management.dictionaries.template.open')}
            </Button>
          ) : null}
        </div>
      )}
      {change.isError ? <Failure detail={describeError(change.error)} /> : null}
      {opened ? template : null}
    </li>
  );
}

function AddEntry({ kind }: { kind: DictionaryKind }) {
  const { t } = useTranslation();
  const change = useDictionaryChange();
  const [name, setName] = useState('');
  const [orgKind, setOrgKind] = useState<OrganizationKind>('ministry');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    change.mutate(
      { op: 'add', kind, name, ...(kind === 'organizations' ? { orgKind } : {}) },
      { onSuccess: () => setName('') },
    );
  };

  return (
    <form onSubmit={submit} className="mt-3 flex flex-col gap-2">
      <span className="flex flex-wrap items-center gap-2">
        <input
          aria-label={t('management.dictionaries.newName')}
          placeholder={t('management.dictionaries.newName')}
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={kind === 'organizations' ? 300 : 200}
          className={cn(FIELD, 'flex-1 basis-56')}
        />
        {kind === 'organizations' ? (
          <select
            aria-label={t('management.dictionaries.orgKind')}
            value={orgKind}
            onChange={(event) => setOrgKind(event.target.value as OrganizationKind)}
            className={FIELD}
          >
            {ORG_KINDS.map((each) => (
              <option key={each} value={each}>
                {t(`projects.orgs.kinds.${each}`)}
              </option>
            ))}
          </select>
        ) : null}
        <Button
          type="submit"
          look="primary"
          size="small"
          disabled={!name.trim() || change.isPending}
        >
          {t('management.dictionaries.add')}
        </Button>
      </span>
      {change.isError ? <Failure detail={describeError(change.error)} /> : null}
    </form>
  );
}

function StepRow({ type, step, canEdit }: { type: string; step: TemplateStep; canEdit: boolean }) {
  const { t } = useTranslation();
  const change = useStepChange();
  const ids = useId();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(step.name);
  const [offset, setOffset] = useState(step.offset_days);

  const valid = Number.isInteger(offset) && offset >= 0 && offset <= 3650;

  const edit = () => {
    setName(step.name);
    setOffset(step.offset_days);
    change.reset();
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    change.reset();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    change.mutate(
      { op: 'save', type, id: step.id, name, offset_days: offset, version: step.version },
      { onSuccess: () => setEditing(false) },
    );
  };

  return (
    <li className="flex flex-col gap-2 rounded-[var(--radius)] bg-sunken px-3 py-2">
      {editing ? (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
          <label className="flex min-w-0 flex-1 basis-48 flex-col gap-1 text-xs text-ink-muted">
            {t('management.dictionaries.template.name')}
            <input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={200}
              className={FIELD}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-muted" htmlFor={`${ids}-offset`}>
            {t('management.dictionaries.template.offsetLabel')}
            <input
              id={`${ids}-offset`}
              type="number"
              inputMode="numeric"
              min={0}
              max={3650}
              value={Number.isNaN(offset) ? '' : offset}
              onChange={(event) => setOffset(event.target.valueAsNumber)}
              className={cn(FIELD, 'numeric w-24')}
            />
          </label>
          <Button
            type="submit"
            look="primary"
            size="small"
            disabled={!name.trim() || !valid || change.isPending}
          >
            {t('management.dictionaries.save')}
          </Button>
          <Button type="button" size="small" onClick={cancel}>
            {t('management.dictionaries.cancel')}
          </Button>
        </form>
      ) : (
        <div className="flex items-center gap-2">
          <span className="min-w-0 flex-1 text-sm text-ink">{step.name}</span>
          <span className="numeric shrink-0 text-xs text-ink-muted">
            {t('management.dictionaries.template.offset', { count: step.offset_days })}
          </span>
          {canEdit ? (
            <>
              <Button
                look="quiet"
                size="icon"
                aria-label={t('management.dictionaries.template.edit', { name: step.name })}
                onClick={edit}
              >
                <Pencil className="size-4" aria-hidden="true" />
              </Button>
              <Button
                look="quiet"
                size="icon"
                aria-label={t('management.dictionaries.template.remove', { name: step.name })}
                disabled={change.isPending}
                onClick={() =>
                  change.mutate({ op: 'remove', type, id: step.id, version: step.version })
                }
              >
                <Trash2 className="size-4" aria-hidden="true" />
              </Button>
            </>
          ) : null}
        </div>
      )}
      {change.isError ? <Failure detail={describeError(change.error)} /> : null}
    </li>
  );
}

function Template({
  type,
  typeName,
  steps,
  canEdit,
}: {
  type: string;
  typeName: string;
  steps: TemplateStep[];
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const change = useStepChange();
  const [name, setName] = useState('');
  const [offset, setOffset] = useState(30);

  const add = (event: FormEvent) => {
    event.preventDefault();
    change.mutate(
      { op: 'save', type, name, offset_days: offset },
      { onSuccess: () => setName('') },
    );
  };

  return (
    <section
      aria-label={t('management.dictionaries.template.title', { type: typeName })}
      className="mt-1 flex flex-col border-t border-line-accent pt-3"
    >
      <h3 className="text-sm font-semibold text-ink-strong">
        {t('management.dictionaries.template.title', { type: typeName })}
      </h3>
      <p className="mb-3 text-sm text-ink-muted">
        {t('management.dictionaries.template.question')}
      </p>
      {steps.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('management.dictionaries.template.empty')}</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {steps.map((step) => (
            <StepRow key={step.id} type={type} step={step} canEdit={canEdit} />
          ))}
        </ol>
      )}
      {canEdit ? (
        <form onSubmit={add} className="mt-3 flex flex-wrap items-end gap-2">
          <input
            aria-label={t('management.dictionaries.template.name')}
            placeholder={t('management.dictionaries.template.name')}
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={200}
            className={cn(FIELD, 'flex-1 basis-48')}
          />
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            {t('management.dictionaries.template.offsetLabel')}
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={3650}
              value={Number.isNaN(offset) ? '' : offset}
              onChange={(event) => setOffset(event.target.valueAsNumber)}
              className={cn(FIELD, 'numeric w-24')}
            />
          </label>
          <Button
            type="submit"
            size="small"
            disabled={
              !name.trim() ||
              !Number.isInteger(offset) ||
              offset < 0 ||
              offset > 3650 ||
              change.isPending
            }
          >
            {t('management.dictionaries.template.add')}
          </Button>
        </form>
      ) : null}
      {change.isError ? <Failure detail={describeError(change.error)} /> : null}
      <p className="mt-3 text-xs text-ink-muted">{t('management.dictionaries.template.note')}</p>
    </section>
  );
}

function GroupList({
  groups,
  chosen,
  onChoose,
}: {
  groups: DictionaryGroup[];
  chosen: DictionaryKind | null;
  onChoose: (kind: DictionaryKind) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-col gap-1.5">
      {groups.map((group) => (
        <li key={group.kind}>
          <button
            type="button"
            aria-current={chosen === group.kind ? 'true' : undefined}
            onClick={() => onChoose(group.kind)}
            className={cn(
              'flex min-h-touch w-full items-center justify-between gap-3 rounded-[var(--radius)] border px-3 text-left text-sm',
              chosen === group.kind
                ? 'border-line-accent bg-accent-soft text-accent-ink'
                : 'border-line bg-card text-ink hover:bg-hover',
            )}
          >
            <span className="min-w-0 truncate">
              {t(`management.dictionaries.kinds.${group.kind}`)}
            </span>
            <span className="numeric shrink-0 text-xs text-ink-muted">
              {group.entries.filter((entry) => entry.is_active).length}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function DictionariesTab({
  groups,
  templates,
  canEdit,
  compact,
}: {
  groups: DictionaryGroup[];
  templates: Record<string, TemplateStep[]>;
  canEdit: boolean;
  compact: boolean;
}) {
  const { t } = useTranslation();
  // На телефоне сначала список справочников, касание открывает один; на ноутбуке — рядом.
  const [chosen, setChosen] = useState<DictionaryKind | null>(compact ? null : 'project_types');
  const [type, setType] = useState<string | null>(null);
  const group = groups.find((each) => each.kind === chosen) ?? null;
  const typeEntry =
    chosen === 'project_types' && type
      ? group?.entries.find((each) => each.id === type)
      : undefined;

  // Набор статусов задан правилами переходов, регионов — ТЗ: объяснить, почему нет «добавить».
  const fixed =
    group?.kind === 'regions' ||
    group?.kind === 'project_statuses' ||
    group?.kind === 'task_statuses'
      ? group.kind
      : null;

  const choose = (kind: DictionaryKind) => {
    setChosen(kind);
    setType(null);
  };

  const template =
    typeEntry && templates[typeEntry.id] ? (
      <Template
        type={typeEntry.id}
        typeName={typeEntry.name}
        steps={templates[typeEntry.id]!}
        canEdit={canEdit}
      />
    ) : null;

  const entries = group ? (
    <Card
      key={group.kind}
      title={t(`management.dictionaries.kinds.${group.kind}`)}
      question={t('management.dictionaries.note')}
      action={
        compact ? (
          <Button look="quiet" size="small" onClick={() => setChosen(null)}>
            <ChevronLeft className="size-4" aria-hidden="true" />
            {t('management.dictionaries.back')}
          </Button>
        ) : undefined
      }
    >
      {fixed ? (
        <p className="mb-3 text-xs text-ink-muted">{t(`management.dictionaries.fixed.${fixed}`)}</p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {group.entries.map((entry, index) => (
          <EntryRow
            key={entry.id}
            kind={group.kind}
            entry={entry}
            group={group}
            index={index}
            canEdit={canEdit}
            opened={type === entry.id}
            onTemplate={
              group.kind === 'project_types'
                ? () => setType(type === entry.id ? null : entry.id)
                : null
            }
            template={template}
          />
        ))}
      </ul>
      {canEdit && group.can_add ? <AddEntry kind={group.kind} /> : null}
    </Card>
  ) : null;

  if (compact) {
    return group ? (
      entries
    ) : (
      <Card
        title={t('management.dictionaries.title')}
        question={t('management.dictionaries.question')}
      >
        <GroupList groups={groups} chosen={chosen} onChoose={choose} />
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-[minmax(0,14rem)_minmax(0,1fr)] items-start gap-5 2xl:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
      <Card
        title={t('management.dictionaries.title')}
        question={t('management.dictionaries.question')}
      >
        <GroupList groups={groups} chosen={chosen} onChoose={choose} />
      </Card>
      {entries}
    </div>
  );
}
