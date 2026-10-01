/**
 * Вкладка «Письма»: архив писем в порядке лестницы (ТЗ 3.4).
 *
 * На телефоне — список, на ноутбуке и мониторе — таблица (ТЗ 6). Отбор по вопросу берёт
 * строки ответа (`filter.ts`). Помощник вносит письмо: обязательны направление,
 * организация и тема (ТЗ 7 — минимум полей), вносятся только письма, где нужен ответ или
 * действие руководителя либо стоит срок (ТЗ 3.4).
 */

import { ArrowDownLeft, ArrowUpRight, Plus } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { STEP_SIGNAL } from '@/sections/pult/model';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Empty } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { NO_FILTER, filterLetters, isFiltered, type Filter } from './filter';
import {
  LETTER_STATES,
  type Direction,
  type InteractionView,
  type LetterRow,
  type NewLetter,
} from './model';
import { letterNumber, letterStatus, orgName } from './text';
import { useAddLetter } from './useInteraction';

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

interface LettersTabProps {
  view: InteractionView;
  device: Device;
  viewer: Role;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  onOpen: (id: string) => void;
}

export function LettersTab({ view, device, viewer, filter, onFilter, onOpen }: LettersTabProps) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const rows = filterLetters(view, filter);

  return (
    <div className="flex flex-col gap-3">
      <Filters view={view} filter={filter} onFilter={onFilter} count={rows.length}>
        {viewer === 'assistant' && !adding ? (
          <Button size="small" onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden="true" />
            {t('interaction.form.title')}
          </Button>
        ) : null}
      </Filters>
      {adding ? <LetterForm view={view} onDone={() => setAdding(false)} /> : null}
      {rows.length === 0 ? (
        <Empty label={t('interaction.letters.empty')} />
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
                  <LetterBadge row={row} />
                  <span className="text-xs text-ink-muted">{orgName(row.organization)}</span>
                </span>
                <span className="mt-1 block text-[15px] leading-snug text-ink-strong">
                  {row.subject}
                </span>
                <span className="numeric mt-1 block truncate text-xs text-ink-muted">
                  {[t(`interaction.directions.${row.direction}`), letterNumber(t, row)].join(' · ')}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="overflow-hidden rounded-[var(--radius-lg)] border border-line bg-card">
          <table className="w-full table-fixed text-left text-sm">
            <thead className="border-b border-line text-xs text-ink-muted">
              <tr>
                <th className="w-44 px-3 py-2 font-medium">
                  {t('interaction.letters.columns.state')}
                </th>
                <th className="w-12 px-3 py-2 font-medium">
                  <span className="sr-only">{t('interaction.letters.columns.direction')}</span>
                </th>
                <th className="w-44 px-3 py-2 font-medium">
                  {t('interaction.letters.columns.organization')}
                </th>
                <th className="px-3 py-2 font-medium">
                  {t('interaction.letters.columns.subject')}
                </th>
                <th className="w-48 px-3 py-2 font-medium">
                  {t('interaction.letters.columns.number')}
                </th>
                <th className="w-36 px-3 py-2 font-medium">
                  {t('interaction.letters.columns.author')}
                </th>
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
                    <LetterBadge row={row} />
                  </td>
                  <td className="px-3 py-2">
                    <DirectionIcon direction={row.direction} />
                  </td>
                  <td className="px-3 py-2 text-ink">
                    <span className="block truncate">{orgName(row.organization)}</span>
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      className="line-clamp-2 text-left text-ink-strong"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpen(row.id);
                      }}
                    >
                      {row.subject}
                    </button>
                  </td>
                  <td className="numeric px-3 py-2 text-xs text-ink-muted">
                    {letterNumber(t, row)}
                  </td>
                  <td className="px-3 py-2 text-ink">
                    <span className="block truncate">{row.author?.name ?? '—'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function DirectionIcon({ direction }: { direction: Direction }) {
  const { t } = useTranslation();
  const Icon = direction === 'incoming' ? ArrowDownLeft : ArrowUpRight;
  return (
    <span title={t(`interaction.directions.${direction}`)}>
      <Icon className="size-4 text-ink-muted" aria-hidden="true" />
      <span className="sr-only">{t(`interaction.directions.${direction}`)}</span>
    </span>
  );
}

/** Ступень словом и цветом; у письма «по плану» — его состояние, чтобы графа не была пустой. */
export function LetterBadge({ row }: { row: LetterRow }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      {row.step ? (
        <Signal state={STEP_SIGNAL[row.step]}>{t(`pult.steps.${row.step}`)}</Signal>
      ) : (
        <Signal state={row.state === 'answered' ? 'calm' : 'plain'}>
          {t(`interaction.states.${row.state}`)}
        </Signal>
      )}
      <span className="numeric text-xs font-medium text-ink">{letterStatus(t, row)}</span>
      {row.rating ? (
        <span className="text-xs text-ink-muted">{t(`interaction.ratings.${row.rating}`)}</span>
      ) : null}
    </span>
  );
}

function Filters({
  view,
  filter,
  onFilter,
  count,
  children,
}: {
  view: InteractionView;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  count: number;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const chip = (active: boolean) =>
    cn(
      'min-h-touch shrink-0 rounded-[var(--radius-pill)] border px-3 text-xs font-medium whitespace-nowrap md:min-h-9',
      active ? 'border-accent bg-accent-soft text-accent-ink' : 'border-line bg-card text-ink',
    );
  const organization = view.organizations.find((each) => each.id === filter.organization);

  return (
    <div className="flex flex-col gap-2">
      {filter.question ? (
        <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
          <span>
            {[
              t(`interaction.questions.${filter.question}.title`),
              organization ? orgName(organization) : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
          <Button
            size="small"
            look="quiet"
            aria-label={t('interaction.letters.clearLabel', {
              what: t(`interaction.questions.${filter.question}.title`),
            })}
            onClick={() => onFilter(NO_FILTER)}
          >
            {t('interaction.letters.clear')}
          </Button>
        </p>
      ) : null}
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {LETTER_STATES.map((state) => (
          <button
            key={state}
            type="button"
            aria-pressed={filter.state === state}
            className={chip(filter.state === state)}
            onClick={() => onFilter({ ...filter, state: filter.state === state ? null : state })}
          >
            {t(`interaction.states.${state}`)}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="grid grid-cols-2 gap-2 md:contents">
          <select
            aria-label={t('interaction.letters.directionLabel')}
            className={cn(FIELD, 'md:min-h-9')}
            value={filter.direction ?? ''}
            onChange={(event) =>
              onFilter({ ...filter, direction: (event.target.value || null) as Direction | null })
            }
          >
            <option value="">{t('interaction.letters.allDirections')}</option>
            <option value="incoming">{t('interaction.directions.incoming')}</option>
            <option value="outgoing">{t('interaction.directions.outgoing')}</option>
          </select>
          <select
            aria-label={t('interaction.letters.organizationLabel')}
            className={cn(FIELD, 'md:min-h-9')}
            value={filter.organization ?? ''}
            onChange={(event) => onFilter({ ...filter, organization: event.target.value || null })}
          >
            <option value="">{t('interaction.letters.allOrganizations')}</option>
            {view.organizations.map((each) => (
              <option key={each.id} value={each.id}>
                {orgName(each)}
              </option>
            ))}
          </select>
        </div>
        <span className="numeric text-xs text-ink-muted">
          {t('interaction.letters.count', { count })}
        </span>
        {isFiltered(filter) && !filter.question ? (
          <Button size="small" look="quiet" onClick={() => onFilter(NO_FILTER)}>
            {t('interaction.letters.clear')}
          </Button>
        ) : null}
        <span className="ml-auto">{children}</span>
      </div>
    </div>
  );
}

function LetterForm({ view, onDone }: { view: InteractionView; onDone: () => void }) {
  const { t } = useTranslation();
  const add = useAddLetter();
  const today = view.as_of.slice(0, 10);
  const [form, setForm] = useState<NewLetter>({
    direction: 'outgoing',
    organization_id: view.organizations[0]?.id ?? '',
    subject: '',
    number: null,
    sent_on: today,
    due_on: null,
    author_id: null,
  });
  const set = (patch: Partial<NewLetter>) => setForm({ ...form, ...patch });
  const label = 'flex flex-col gap-1 text-xs text-ink-muted';

  return (
    <Card title={t('interaction.form.title')} question={t('interaction.form.hint')}>
      <form
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!form.subject.trim()) return;
          add.mutate(form, { onSuccess: onDone });
        }}
      >
        <label className={label}>
          {t('interaction.form.direction')}
          <select
            className={FIELD}
            value={form.direction}
            onChange={(event) => set({ direction: event.target.value as Direction })}
          >
            <option value="outgoing">{t('interaction.directions.outgoing')}</option>
            <option value="incoming">{t('interaction.directions.incoming')}</option>
          </select>
        </label>
        <label className={label}>
          {t('interaction.form.organization')}
          <select
            className={FIELD}
            value={form.organization_id}
            onChange={(event) => set({ organization_id: event.target.value })}
          >
            {view.organizations.map((each) => (
              <option key={each.id} value={each.id}>
                {orgName(each)}
              </option>
            ))}
          </select>
        </label>
        <label className={cn(label, 'sm:col-span-2 lg:col-span-1')}>
          {t('interaction.form.subject')}
          <input
            className={FIELD}
            value={form.subject}
            onChange={(event) => set({ subject: event.target.value })}
            required
          />
        </label>
        <label className={label}>
          {t('interaction.form.number')}
          <input
            className={FIELD}
            value={form.number ?? ''}
            onChange={(event) => set({ number: event.target.value || null })}
          />
        </label>
        <label className={label}>
          {t('interaction.form.sentOn')}
          <input
            type="date"
            className={FIELD}
            value={form.sent_on}
            onChange={(event) => set({ sent_on: event.target.value || today })}
          />
        </label>
        <label className={label}>
          {t('interaction.form.dueOn')}
          <input
            type="date"
            className={FIELD}
            value={form.due_on ?? ''}
            onChange={(event) => set({ due_on: event.target.value || null })}
          />
        </label>
        <label className={label}>
          {t('interaction.form.author')}
          <select
            className={FIELD}
            value={form.author_id ?? ''}
            onChange={(event) => set({ author_id: event.target.value || null })}
          >
            <option value="">{t('interaction.form.noAuthor')}</option>
            {view.people.map((each) => (
              <option key={each.id} value={each.id}>
                {each.name}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-end gap-2 sm:col-span-2 lg:col-span-3">
          <Button type="submit" look="primary" disabled={add.isPending || !form.subject.trim()}>
            {t('interaction.form.add')}
          </Button>
          <Button type="button" look="quiet" onClick={onDone}>
            {t('interaction.form.cancel')}
          </Button>
          {form.due_on ? null : (
            <span className="text-xs text-ink-muted">
              {t('interaction.form.dueHint', { days: view.thresholds.quiet_days })}
            </span>
          )}
        </div>
      </form>
    </Card>
  );
}
