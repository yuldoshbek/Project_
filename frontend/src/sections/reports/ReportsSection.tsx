/**
 * Доклады и мероприятия — «готовы ли мы к дате и кто задерживает?» (ТЗ 2, 3.5).
 *
 * Сверху — два вопроса с ответом и действием; ниже — подготовки в порядке лестницы: дни до
 * показа, этап, каких сведений не хватает и кто задерживает. Касание открывает карточку:
 * этап, чек-лист, запросы сведений и напоминание тому, кто задерживает (критерий 5 блока 2).
 * Помощник заводит подготовку; руководитель смотрит и решает кнопками Пульта.
 */

import { Plus, Presentation } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { STEP_SIGNAL } from '@/sections/pult/model';
import { describeError } from '@/shared/api/client';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { formatDate, formatDateTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Sheet } from '@/shared/ui/Sheet';
import { Empty, Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';
import { useLinkedOpen } from '@/shared/lib/useLinkedOpen';

import {
  ADDRESSEES,
  type Addressee,
  type NewPreparation,
  type PreparationKind,
  type PreparationRow,
  type ReportsView,
} from './model';
import { PrepPanel } from './PrepPanel';
import { answerText, daysLeftText, delayText, missingText } from './text';
import { useCreatePreparation, useReports } from './useReports';

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

export function ReportsSection() {
  const reports = useReports();
  if (reports.isPending) return <Loading />;
  if (reports.isError) {
    return <Failure detail={describeError(reports.error)} onRetry={() => void reports.refetch()} />;
  }
  return <Reports view={reports.data} />;
}

function Reports({ view }: { view: ReportsView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  const viewer: Role = user.data?.role === 'leader' ? 'leader' : 'assistant';
  // Карточка из ссылки — так её открывают Календарь и поиск.
  const [open, setOpen] = useLinkedOpen();
  const [only, setOnly] = useState<string[] | null>(null);
  const [adding, setAdding] = useState(false);
  const freshness = t('reports.freshness', { when: formatDateTime(view.as_of) });
  const rows = only ? view.items.filter((each) => only.includes(each.id)) : view.items;

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <header className="flex flex-wrap items-center gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {device === 'phone' ? null : (
            <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
              <Presentation className="size-5" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-ink-strong">{t('sections.reports')}</h1>
            <p className="text-sm text-ink-muted">{t('sectionQuestions.reports')}</p>
            {view.is_demo ? (
              <p className="mt-1 text-xs">
                <span title={t('pult.demoHint')}>
                  <Signal state="wait">{t('pult.demo')}</Signal>
                </span>
              </p>
            ) : null}
          </div>
        </div>
        {viewer === 'assistant' && !adding ? (
          <Button onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden="true" />
            {t('reports.form.title')}
          </Button>
        ) : null}
      </header>

      {adding ? <PrepForm view={view} onDone={() => setAdding(false)} /> : null}

      <div className={cn('grid gap-3', device === 'phone' ? 'grid-cols-1' : 'grid-cols-2 gap-4')}>
        {view.questions.map((answer) => {
          const text = answerText(t, answer);
          return (
            <Card
              key={answer.key}
              title={t(`reports.questions.${answer.key}.title`)}
              freshness={freshness}
              className="flex flex-col"
            >
              <p className="text-lg leading-snug font-semibold text-ink-strong">{text.main}</p>
              {text.detail ? <p className="mt-1 text-sm text-ink-muted">{text.detail}</p> : null}
              {text.empty ? null : (
                <div className="mt-auto pt-3">
                  <Button
                    size="small"
                    onClick={() =>
                      answer.key === 'readiness' && answer.nearest
                        ? setOpen(answer.nearest.id)
                        : setOnly(answer.rows)
                    }
                  >
                    {t(`reports.questions.${answer.key}.action`)}
                  </Button>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      <section aria-label={t('reports.list.label')} className="flex flex-col gap-2">
        {only ? (
          <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
            {t('reports.list.filtered', { count: rows.length })}
            <Button size="small" look="quiet" onClick={() => setOnly(null)}>
              {t('reports.list.clear')}
            </Button>
          </p>
        ) : null}
        {rows.length === 0 ? (
          <Empty label={t('reports.list.empty')} />
        ) : (
          <ul
            className={cn(
              'grid gap-2',
              device === 'phone' ? 'grid-cols-1' : 'grid-cols-2 gap-3',
              device === 'monitor' && 'grid-cols-3 gap-4',
            )}
          >
            {rows.map((row) => (
              <li
                key={row.id}
                className="min-w-0 rounded-[var(--radius-lg)] border border-line bg-card"
              >
                <button
                  type="button"
                  onClick={() => setOpen(row.id)}
                  className="flex min-h-touch w-full flex-col gap-2 p-4 text-left"
                >
                  <PrepBadge row={row} />
                  <span className="font-semibold text-ink-strong">{row.title}</span>
                  <span className="numeric text-xs text-ink-muted">
                    {[
                      t(`reports.kinds.${row.kind}`),
                      row.addressee ? t(`reports.addressees.${row.addressee}`) : null,
                      formatDate(row.show_on),
                      row.responsible?.name ?? null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                  <span className="text-sm text-ink">{missingText(t, row)}</span>
                  {row.delays[0] ? (
                    <span className="text-sm text-burn-ink">{delayText(t, row.delays[0])}</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {open ? (
        <Sheet
          label={t('reports.card.label')}
          closeLabel={t('reports.card.close')}
          onClose={() => setOpen(null)}
          wide
        >
          <PrepPanel id={open} view={view} viewer={viewer} />
        </Sheet>
      ) : null}
    </div>
  );
}

export function PrepBadge({ row }: { row: PreparationRow }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      {row.step ? (
        <Signal state={STEP_SIGNAL[row.step]}>{t(`pult.steps.${row.step}`)}</Signal>
      ) : (
        <Signal state={row.stage === 'shown' ? 'calm' : 'plain'}>
          {t(`reports.stages.${row.stage}`)}
        </Signal>
      )}
      <span className="numeric text-xs font-medium text-ink">{daysLeftText(t, row)}</span>
      {row.step ? (
        <span className="text-xs text-ink-muted">{t(`reports.stages.${row.stage}`)}</span>
      ) : null}
    </span>
  );
}

function PrepForm({ view, onDone }: { view: ReportsView; onDone: () => void }) {
  const { t } = useTranslation();
  const create = useCreatePreparation();
  const [form, setForm] = useState<NewPreparation>({
    kind: 'report',
    title: '',
    show_on: view.as_of.slice(0, 10),
    start_on: null,
    addressee: null,
    responsible_id: null,
    project_id: null,
  });
  const set = (patch: Partial<NewPreparation>) => setForm({ ...form, ...patch });
  const label = 'flex flex-col gap-1 text-xs text-ink-muted';

  return (
    <Card title={t('reports.form.title')} question={t('reports.form.hint')}>
      <form
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!form.title.trim()) return;
          create.mutate(form, { onSuccess: onDone });
        }}
      >
        <label className={label}>
          {t('reports.form.kind')}
          <select
            className={FIELD}
            value={form.kind}
            onChange={(event) => {
              const kind = event.target.value as PreparationKind;
              set({ kind, addressee: kind === 'report' ? form.addressee : null });
            }}
          >
            <option value="report">{t('reports.kinds.report')}</option>
            <option value="event">{t('reports.kinds.event')}</option>
          </select>
        </label>
        <label className={cn(label, 'sm:col-span-2 lg:col-span-2')}>
          {t('reports.form.name')}
          <input
            className={FIELD}
            value={form.title}
            onChange={(event) => set({ title: event.target.value })}
            required
          />
        </label>
        <label className={label}>
          {t('reports.form.showOn')}
          <input
            type="date"
            className={FIELD}
            value={form.show_on}
            onChange={(event) => set({ show_on: event.target.value || form.show_on })}
          />
        </label>
        <label className={label}>
          {t('reports.form.startOn')}
          <input
            type="date"
            className={FIELD}
            value={form.start_on ?? ''}
            onChange={(event) => set({ start_on: event.target.value || null })}
          />
        </label>
        {form.kind === 'report' ? (
          <label className={label}>
            {t('reports.form.addressee')}
            <select
              className={FIELD}
              value={form.addressee ?? ''}
              onChange={(event) =>
                set({ addressee: (event.target.value || null) as Addressee | null })
              }
            >
              <option value="">{t('reports.form.none')}</option>
              {ADDRESSEES.map((each) => (
                <option key={each} value={each}>
                  {t(`reports.addressees.${each}`)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className={label}>
          {t('reports.form.responsible')}
          <select
            className={FIELD}
            value={form.responsible_id ?? ''}
            onChange={(event) => set({ responsible_id: event.target.value || null })}
          >
            <option value="">{t('reports.form.none')}</option>
            {view.people.map((each) => (
              <option key={each.id} value={each.id}>
                {each.name}
              </option>
            ))}
          </select>
        </label>
        <label className={label}>
          {t('reports.form.project')}
          <select
            className={FIELD}
            value={form.project_id ?? ''}
            onChange={(event) => set({ project_id: event.target.value || null })}
          >
            <option value="">{t('reports.form.none')}</option>
            {view.projects.map((each) => (
              <option key={each.id} value={each.id}>
                {t('reports.form.projectOption', { code: each.code, title: each.title })}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-end gap-2 sm:col-span-2 lg:col-span-3">
          <Button type="submit" look="primary" disabled={create.isPending || !form.title.trim()}>
            {t('reports.form.add')}
          </Button>
          <Button type="button" look="quiet" onClick={onDone}>
            {t('reports.form.cancel')}
          </Button>
        </div>
      </form>
    </Card>
  );
}
