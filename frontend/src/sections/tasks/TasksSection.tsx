/**
 * Задачи — «что делать, кому и к какому сроку» (ТЗ 2).
 *
 * Раскладка меняется с устройством (`app/device.ts`):
 *
 * - **телефон** — строка ввода, список по сроку, под ним «Кто перегружен?»; таблиц нет
 *   (ТЗ 6); карточка задачи — листом;
 * - **ноутбук** — список или таблица, рядом «Кто перегружен?»; карточка — листом;
 * - **монитор** — три панели: список, раскрытая задача, «Кто перегружен?». Не одна широкая
 *   колонка и пустота (аудит 20.09, В8).
 *
 * Строка ввода — только у помощника: данные вносит он (ТЗ 1). Руководитель смотрит и
 * фильтрует касанием по «Кто перегружен?».
 */

import { ListChecks, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDateTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Sheet } from '@/shared/ui/Sheet';
import { Empty, Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';
import { useLinkedOpen } from '@/shared/lib/useLinkedOpen';

import { CaptureLine } from './CaptureLine';
import { filterTasks, isFiltered, NO_FILTER, type TaskFilter } from './filter';
import { LoadCard } from './LoadCard';
import type { TasksView } from './model';
import { TaskList } from './TaskList';
import { projectLabel } from './text';
import { TaskPanel } from './TaskPanel';
import { TaskTable } from './TaskTable';
import { useTasks } from './useTasks';

type View = 'list' | 'table';

const VIEWS: readonly View[] = ['list', 'table'];

/** Сколько секунд видно «Задача заведена». */
const NOTICE_SECONDS = 6;

export function TasksSection() {
  const tasks = useTasks();
  if (tasks.isPending) return <Loading />;
  if (tasks.isError) {
    return <Failure detail={describeError(tasks.error)} onRetry={() => void tasks.refetch()} />;
  }
  return <Tasks view={tasks.data} />;
}

function Tasks({ view }: { view: TasksView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  const canEdit = user.data?.role !== 'leader';
  const isPhone = device === 'phone';
  const isMonitor = device === 'monitor';

  const [mode, setMode] = useState<View>('list');
  const [filter, setFilter] = useState<TaskFilter>(NO_FILTER);
  // Карточка из ссылки — так её открывают Календарь и поиск.
  const [open, setOpen] = useLinkedOpen();
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), NOTICE_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const items = useMemo(() => filterTasks(view.items, filter), [view.items, filter]);
  const closePanel = useCallback(() => setOpen(null), [setOpen]);
  const person = view.people.find((each) => each.id === filter.assignee);

  const pick = (personId: string) =>
    setFilter({ ...filter, assignee: filter.assignee === personId ? '' : personId });

  // Монитор: раскрытая задача — в средней панели, по умолчанию первая в списке.
  const selected = isMonitor ? (open ?? items[0]?.id ?? null) : open;

  const panel = (id: string) => (
    <TaskPanel
      key={id}
      id={id}
      canEdit={canEdit}
      types={view.types}
      people={view.people}
      projects={view.projects}
    />
  );

  const list =
    items.length === 0 ? (
      <Empty label={t('tasks.filters.empty')} />
    ) : mode === 'table' && !isPhone ? (
      <TaskTable items={items} onOpen={setOpen} />
    ) : (
      <TaskList items={items} onOpen={setOpen} selected={isMonitor ? selected : null} />
    );

  const load = (
    <LoadCard load={view.load} asOf={view.as_of} active={filter.assignee || null} onPick={pick} />
  );

  return (
    <div className={cn('flex flex-col', isPhone ? 'gap-3' : 'gap-5')}>
      <Header
        view={view}
        compact={isPhone}
        total={items.length}
        mode={isPhone ? null : mode}
        onMode={setMode}
      />

      {canEdit ? (
        <CaptureLine
          types={view.types}
          people={view.people}
          projects={view.projects}
          compact={isPhone}
          onCreated={(task) => setNotice(t('tasks.capture.created', { code: task.code }))}
        />
      ) : null}

      <Filters view={view} filter={filter} onFilter={setFilter} compact={isPhone} />

      {person ? (
        <div className="flex items-center gap-2">
          <p className="min-w-0 flex-1 truncate text-sm text-ink-muted">
            {t('tasks.load.filtered', { name: person.name })}
          </p>
          <Button look="quiet" size="small" onClick={() => setFilter({ ...filter, assignee: '' })}>
            {t('tasks.load.showAll')}
          </Button>
        </div>
      ) : null}

      {isPhone ? (
        <>
          {list}
          {load}
        </>
      ) : isMonitor ? (
        <div className="grid grid-cols-[minmax(0,5fr)_minmax(0,4fr)_minmax(0,3fr)] items-start gap-6">
          <div className="min-w-0">{list}</div>
          <Card
            title={t('tasks.panel.title')}
            className="sticky top-[calc(var(--topbar-height)+2rem)]"
          >
            {selected ? (
              panel(selected)
            ) : (
              <p className="text-sm text-ink-muted">{t('tasks.panel.pick')}</p>
            )}
          </Card>
          <div className="flex flex-col gap-6">{load}</div>
        </div>
      ) : (
        <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] items-start gap-5">
          <div className="min-w-0">{list}</div>
          <div className="flex flex-col gap-5">{load}</div>
        </div>
      )}

      {open && !isMonitor ? (
        <Sheet
          label={t('sections.tasks')}
          closeLabel={t('tasks.panel.close')}
          onClose={closePanel}
          wide
        >
          {panel(open)}
        </Sheet>
      ) : null}

      {notice ? (
        <p
          role="status"
          className={cn(
            'fixed inset-x-4 z-50 mx-auto max-w-xl rounded-[var(--radius-lg)] border border-line',
            'bg-raised px-4 py-3 text-sm text-ink shadow-raised',
            isPhone ? 'bottom-[calc(env(safe-area-inset-bottom)+4.75rem)]' : 'bottom-6',
          )}
        >
          {notice}
        </p>
      ) : null}
    </div>
  );
}

function Header({
  view,
  compact,
  total,
  mode,
  onMode,
}: {
  view: TasksView;
  compact: boolean;
  total: number;
  mode: View | null;
  onMode: (mode: View) => void;
}) {
  const { t } = useTranslation();
  const demo = view.is_demo ? (
    <span title={t('pult.demoHint')}>
      <Signal state="wait">{t('pult.demo')}</Signal>
    </span>
  ) : null;

  if (compact) {
    return (
      <header className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-ink-strong">{t('sections.tasks')}</h1>
          <span className="numeric min-w-0 flex-1 truncate text-xs text-ink-muted">
            {t('tasks.count', { count: total })}
          </span>
        </div>
        {demo ? <div className="flex text-xs">{demo}</div> : null}
      </header>
    );
  }

  return (
    <header className="flex flex-wrap items-center gap-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <ListChecks className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-ink-strong">{t('sections.tasks')}</h1>
          <p className="text-sm text-ink-muted">{t('sectionQuestions.tasks')}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>{t('pult.asOf', { when: formatDateTime(view.as_of) })}</span>
            <span className="numeric">{t('tasks.count', { count: total })}</span>
            {demo}
          </p>
        </div>
      </div>
      {mode ? (
        <span role="tablist" aria-label={t('tasks.views.label')} className="inline-flex gap-1">
          {VIEWS.map((each) => (
            <button
              key={each}
              type="button"
              role="tab"
              aria-selected={mode === each}
              onClick={() => onMode(each)}
              className={cn(
                'min-h-touch rounded-[var(--radius-pill)] border px-4 text-sm font-medium',
                'transition-colors duration-[var(--motion-fast)]',
                mode === each
                  ? 'border-accent bg-accent text-ink-inverse'
                  : 'border-line bg-card text-ink hover:bg-hover',
              )}
            >
              {t(`tasks.views.${each}`)}
            </button>
          ))}
        </span>
      ) : null}
    </header>
  );
}

function Filters({
  view,
  filter,
  onFilter,
  compact,
}: {
  view: TasksView;
  filter: TaskFilter;
  onFilter: (filter: TaskFilter) => void;
  /** Телефон: поиск и «требует внимания»; остальное — касанием по «Кто перегружен?». */
  compact: boolean;
}) {
  const { t } = useTranslation();
  const set = (patch: Partial<TaskFilter>) => onFilter({ ...filter, ...patch });
  const field =
    'min-h-touch rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="relative min-w-0 flex-1 basis-56">
        <span className="sr-only">{t('tasks.filters.search')}</span>
        <Search
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-muted"
          aria-hidden="true"
        />
        <input
          type="search"
          value={filter.search}
          onChange={(event) => set({ search: event.target.value })}
          placeholder={t('tasks.filters.search')}
          className={cn(field, 'w-full pl-8')}
        />
      </label>

      {!compact ? (
        <>
          <label>
            <span className="sr-only">{t('tasks.table.assignee')}</span>
            <select
              value={filter.assignee}
              onChange={(event) => set({ assignee: event.target.value })}
              className={field}
            >
              <option value="">{t('tasks.filters.anyone')}</option>
              {view.people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">{t('tasks.table.type')}</span>
            <select
              value={filter.type}
              onChange={(event) => set({ type: event.target.value })}
              className={field}
            >
              <option value="">{t('tasks.filters.anyType')}</option>
              {view.types.map((type) => (
                <option key={type.code} value={type.code}>
                  {type.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">{t('tasks.panel.project')}</span>
            <select
              value={filter.project}
              onChange={(event) => set({ project: event.target.value })}
              className={cn(field, 'max-w-56')}
            >
              <option value="">{t('tasks.filters.anyProject')}</option>
              <option value="none">{t('tasks.filters.noProject')}</option>
              {view.projects.map((ref) => (
                <option key={ref.id} value={ref.id}>
                  {projectLabel(ref)}
                </option>
              ))}
            </select>
          </label>
        </>
      ) : null}

      <button
        type="button"
        aria-pressed={filter.attention}
        onClick={() => set({ attention: !filter.attention })}
        className={cn(
          'min-h-touch rounded-[var(--radius-pill)] border px-3 text-sm',
          'transition-colors duration-[var(--motion-fast)]',
          filter.attention
            ? 'border-line-accent bg-accent-soft text-accent-ink'
            : 'border-line bg-card text-ink hover:bg-hover',
        )}
      >
        {t('tasks.filters.attention')}
      </button>

      {isFiltered(filter) ? (
        <Button look="quiet" onClick={() => onFilter(NO_FILTER)}>
          {t('tasks.filters.clear')}
        </Button>
      ) : null}
    </div>
  );
}
