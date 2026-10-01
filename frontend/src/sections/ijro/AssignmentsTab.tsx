/**
 * Вкладка «Поручения»: реестр в порядке лестницы.
 *
 * Телефон — список (ТЗ 6: без таблиц); ноутбук и монитор — таблица. Строка несёт ступень и
 * дни, документ и пункт, первую строку содержания как в источнике, ответственного и
 * головного исполнителя. В списке вопроса «работает ли ответственный?» контрольная отметка
 * ставится прямо в строке — одним касанием (критерий 3 блока 2, V35).
 */

import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { STEP_SIGNAL, type Step } from '@/sections/pult/model';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Empty } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { NO_FILTER, applyFilter, isFiltered, type Filter } from './filter';
import {
  MARK_KINDS,
  SOURCES,
  STAGES,
  type AssignmentRow,
  type IjroSource,
  type IjroView,
  type Stage,
} from './model';
import { dueLabel, firstLine, leadName, place, stepText, who } from './text';
import { useMark } from './useIjro';

const STEPS: readonly Step[] = [
  'awaiting_decision',
  'overdue',
  'burning',
  'blocked_by_others',
  'silent',
];

interface AssignmentsTabProps {
  view: IjroView;
  device: Device;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  onOpen: (id: string) => void;
}

export function AssignmentsTab({ view, device, filter, onFilter, onOpen }: AssignmentsTabProps) {
  const { t } = useTranslation();
  const rows = applyFilter(view, filter);
  const marking = filter.question === 'silent';

  return (
    <div className="flex flex-col gap-3">
      <Filters view={view} filter={filter} onFilter={onFilter} count={rows.length} />
      {rows.length === 0 ? (
        <Empty label={t('ijro.list.empty')} />
      ) : device === 'phone' ? (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => (
            <li key={row.id} className="rounded-[var(--radius)] border border-line bg-card">
              <button
                type="button"
                onClick={() => onOpen(row.id)}
                className="block min-h-touch w-full p-3 text-left"
              >
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <StepBadge row={row} />
                  <span className="numeric text-xs text-ink-muted">{place(row)}</span>
                </span>
                <span className="mt-1 block text-[15px] leading-snug text-ink-strong">
                  {firstLine(row.content, 80)}
                </span>
                <span className="mt-1 block truncate text-xs text-ink-muted">
                  {[who(row), dueLabel(t, row), leadText(t, row)].filter(Boolean).join(' · ')}
                </span>
              </button>
              {marking ? <MarkRow id={row.id} /> : null}
            </li>
          ))}
        </ul>
      ) : (
        <div className="overflow-hidden rounded-[var(--radius-lg)] border border-line bg-card">
          <table className="w-full table-fixed text-left text-sm">
            <thead className="border-b border-line text-xs text-ink-muted">
              <tr>
                <th className="w-36 px-3 py-2 font-medium">{t('ijro.list.columns.step')}</th>
                <th className="w-32 px-3 py-2 font-medium">{t('ijro.list.columns.due')}</th>
                <th className="w-36 px-3 py-2 font-medium">{t('ijro.list.columns.place')}</th>
                <th className="px-3 py-2 font-medium">{t('ijro.list.columns.content')}</th>
                <th className="w-40 px-3 py-2 font-medium">{t('ijro.list.columns.responsible')}</th>
                <th className="w-28 px-3 py-2 font-medium">{t('ijro.list.columns.stage')}</th>
                <th className="w-32 px-3 py-2 font-medium">{t('ijro.list.columns.life')}</th>
                {marking ? (
                  <th className="w-72 px-3 py-2 font-medium">{t('ijro.list.columns.mark')}</th>
                ) : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => onOpen(row.id)}
                  className="cursor-pointer align-top hover:bg-hover"
                >
                  <td className="px-3 py-2">
                    <StepBadge row={row} />
                  </td>
                  <td className="numeric px-3 py-2 text-ink">
                    {dueLabel(t, row)}
                    {row.extensions > 0 && row.original_due_on ? (
                      <span className="block text-xs text-ink-muted">
                        {t('ijro.list.original', { date: formatDate(row.original_due_on) })}
                      </span>
                    ) : null}
                  </td>
                  <td className="numeric px-3 py-2 text-ink-muted">{place(row)}</td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      className="line-clamp-2 text-left text-ink-strong"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpen(row.id);
                      }}
                    >
                      {row.content}
                    </button>
                  </td>
                  <td className="px-3 py-2 text-ink">
                    <span className="block truncate">{who(row)}</span>
                    {leadName(row) ? (
                      <span className="block truncate text-xs text-ink-muted">
                        {leadText(t, row)}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-ink">{t(`ijro.stages.${row.stage}`)}</td>
                  <td className="numeric px-3 py-2 text-xs text-ink-muted">
                    {row.sign_of_life
                      ? t(`ijro.life.${row.sign_of_life.source}`, {
                          date: formatDate(row.sign_of_life.on),
                        })
                      : t('ijro.life.none')}
                  </td>
                  {marking ? (
                    <td className="px-3 py-1" onClick={(event) => event.stopPropagation()}>
                      <MarkRow id={row.id} />
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function leadText(t: ReturnType<typeof useTranslation>['t'], row: AssignmentRow): string | null {
  const name = leadName(row);
  return name ? t('ijro.lead.coExecutor', { name }) : null;
}

/** Ступень словом и цветом; у строки «по плану» — этап, чтобы графа не была пустой. */
export function StepBadge({ row }: { row: Pick<AssignmentRow, 'step' | 'deviation' | 'stage'> }) {
  const { t } = useTranslation();
  if (!row.step) return <Signal state="plain">{t(`ijro.stages.${row.stage}`)}</Signal>;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      <Signal state={STEP_SIGNAL[row.step]}>{t(`pult.steps.${row.step}`)}</Signal>
      <span className="numeric text-xs font-medium text-ink">{stepText(t, row)}</span>
    </span>
  );
}

/** Контрольная отметка в одно касание: три вида, без формы. */
export function MarkRow({ id }: { id: string }) {
  const { t } = useTranslation();
  const mark = useMark();
  return (
    <div className="flex flex-wrap gap-1 border-t border-line p-2 lg:border-0 lg:p-0">
      {MARK_KINDS.map((kind) => (
        <Button
          key={kind}
          size="small"
          disabled={mark.isPending}
          onClick={() => mark.mutate({ id, kind })}
        >
          {t(`ijro.marks.${kind}`)}
        </Button>
      ))}
    </div>
  );
}

function Filters({
  view,
  filter,
  onFilter,
  count,
}: {
  view: IjroView;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  count: number;
}) {
  const { t } = useTranslation();
  const chip = (active: boolean) =>
    cn(
      'min-h-touch rounded-[var(--radius-pill)] border px-3 text-xs font-medium md:min-h-9',
      active ? 'border-accent bg-accent-soft text-accent-ink' : 'border-line bg-card text-ink',
    );
  const select =
    'min-h-touch min-w-0 flex-1 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink md:min-h-9 md:flex-none';

  // Что сузило список по действию виджета — названо словами и снимается одним касанием.
  const person = filter.person
    ? (view.people.find((each) => each.id === filter.person)?.name ??
      filter.person.replace(/^raw:/, ''))
    : null;
  const organization = view.organizations.find((each) => each.id === filter.organization);
  const document = view.documents.find((each) => each.document.id === filter.document)?.document;
  const pinned: { label: string; clear: Partial<Filter> }[] = [
    ...(filter.question
      ? [{ label: t(`ijro.questions.${filter.question}.title`), clear: { question: null } }]
      : []),
    ...(person ? [{ label: person, clear: { person: null } }] : []),
    ...(organization
      ? [{ label: organization.short_name ?? organization.name, clear: { organization: null } }]
      : []),
    ...(document ? [{ label: document.code, clear: { document: null } }] : []),
  ];

  return (
    <div className="flex flex-col gap-2">
      {pinned.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          {pinned.map((each) => (
            <button
              key={each.label}
              type="button"
              className={cn(chip(true), 'inline-flex items-center gap-1')}
              aria-label={t('ijro.list.clearOne', { name: each.label })}
              onClick={() => onFilter({ ...filter, ...each.clear })}
            >
              <span className="max-w-64 truncate">{each.label}</span>
              <X className="size-3.5 shrink-0" aria-hidden="true" />
            </button>
          ))}
        </div>
      ) : null}
      {/* Ступени — одной строкой с прокруткой внутри: пять фишек в три ряда отнимали у
          телефона пол-экрана до первой строки списка. */}
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {STEPS.map((step) => (
          <button
            key={step}
            type="button"
            aria-pressed={filter.step === step}
            className={cn(chip(filter.step === step), 'shrink-0 whitespace-nowrap')}
            onClick={() => onFilter({ ...filter, step: filter.step === step ? null : step })}
          >
            {t(`pult.steps.${step}`)}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {/* На телефоне выборы — своей строкой пополам: рядом со счётчиком они сжимались
            до «Все ис…». На ноутбуке обёртки нет — они стоят в общей строке. */}
        <div className="grid w-full grid-cols-2 gap-2 md:contents">
          <select
            aria-label={t('ijro.list.source')}
            className={select}
            value={filter.source ?? ''}
            onChange={(event) =>
              onFilter({ ...filter, source: (event.target.value || null) as IjroSource | null })
            }
          >
            <option value="">{t('ijro.list.anySource')}</option>
            {SOURCES.map((source) => (
              <option key={source} value={source}>
                {t(`ijro.sources.${source}`)}
              </option>
            ))}
          </select>
          <select
            aria-label={t('ijro.list.stage')}
            className={select}
            value={filter.stage ?? ''}
            onChange={(event) =>
              onFilter({ ...filter, stage: (event.target.value || null) as Stage | null })
            }
          >
            <option value="">{t('ijro.list.anyStage')}</option>
            {STAGES.map((stage) => (
              <option key={stage} value={stage}>
                {t(`ijro.stages.${stage}`)}
              </option>
            ))}
          </select>
        </div>
        <span className="numeric text-xs text-ink-muted">
          {t('ijro.list.count', { count, total: view.items.length })}
        </span>
        {isFiltered(filter) ? (
          <Button look="quiet" size="small" onClick={() => onFilter(NO_FILTER)}>
            {t('ijro.list.clear')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
