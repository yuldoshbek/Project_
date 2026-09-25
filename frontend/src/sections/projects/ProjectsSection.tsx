/**
 * Проекты — «где мы по каждому проекту и подпроекту» (ТЗ 5).
 *
 * Раскладка меняется с устройством (`app/device.ts`):
 *
 * - **телефон** — список плиток по статусу: переключатель «В работе / На паузе / …» вместо
 *   колонок доски, таблиц и таймлайна нет (ТЗ 6);
 * - **ноутбук и монитор** — три вида: доска по статусам, таблица, таймлайн.
 *
 * Порядок внутри любого вида — серверный: сначала то, что требует внимания, в порядке
 * лестницы. Фильтры его не меняют, а только убирают лишнее.
 *
 * Карточка проекта и форма нового проекта открываются листом поверх раздела: закрыл — и
 * вернулся туда же, с теми же фильтрами.
 */

import { FolderKanban, Plus, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDateTime, localDay } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Sheet } from '@/shared/ui/Sheet';
import { Empty, Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { Board } from './Board';
import { CreateProject } from './CreateProject';
import { filterProjects, isFiltered, NO_FILTER, type ProjectFilter } from './filter';
import {
  BOARD_COLUMNS,
  NEEDS_REASON,
  TERMINAL,
  type ProjectCard,
  type ProjectStatus,
  type ProjectsView,
} from './model';
import { ProjectPanel } from './ProjectPanel';
import { ProjectTile } from './ProjectTile';
import { StatusReason } from './StatusReason';
import { Table } from './Table';
import { Timeline } from './Timeline';
import { useProjects, useProjectStatus } from './useProjects';

type View = 'board' | 'table' | 'timeline';

const VIEWS: readonly View[] = ['board', 'table', 'timeline'];

/** Сколько секунд видно «Проект заведён». */
const NOTICE_SECONDS = 6;

export function ProjectsSection() {
  const projects = useProjects();

  if (projects.isPending) return <Loading />;
  if (projects.isError) {
    return (
      <Failure detail={describeError(projects.error)} onRetry={() => void projects.refetch()} />
    );
  }
  return <Projects view={projects.data} />;
}

function Projects({ view }: { view: ProjectsView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  const status = useProjectStatus();

  // Вносит данные помощник, руководитель смотрит (ТЗ 1). Сервер проверяет то же сам.
  const canEdit = user.data?.role !== 'leader';
  const isPhone = device === 'phone';
  const today = localDay(view.as_of);

  const [mode, setMode] = useState<View>('board');
  const [filter, setFilter] = useState<ProjectFilter>(NO_FILTER);
  const [phoneStatus, setPhoneStatus] = useState<ProjectStatus>('in_progress');
  const [open, setOpen] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [move, setMove] = useState<{ card: ProjectCard; status: ProjectStatus } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), NOTICE_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const items = useMemo(() => filterProjects(view.items, filter), [view.items, filter]);
  const programs = useMemo(
    () => view.items.filter((card) => card.is_multiyear && !TERMINAL.has(card.status)),
    [view.items],
  );

  const onMove = (id: string, next: ProjectStatus) => {
    const card = view.items.find((each) => each.id === id);
    if (!card || !canEdit) return;
    if (NEEDS_REASON.has(next)) setMove({ card, status: next });
    else status.mutate({ id, status: next, reason: null });
  };

  const closePanel = useCallback(() => setOpen(null), []);
  const closeCreate = useCallback(() => setCreating(false), []);
  const closeMove = useCallback(() => setMove(null), []);

  const phoneItems = items.filter((card) => card.status === phoneStatus);

  return (
    <div className={cn('flex flex-col', isPhone ? 'gap-3' : 'gap-5')}>
      <Header
        view={view}
        compact={isPhone}
        total={items.length}
        mode={isPhone ? null : mode}
        onMode={setMode}
        onCreate={canEdit ? () => setCreating(true) : null}
      />

      <Filters view={view} filter={filter} onFilter={setFilter} compact={isPhone} />

      {status.isError ? (
        <Failure detail={describeError(status.error)} onRetry={() => status.reset()} />
      ) : null}

      {items.length === 0 ? (
        <Empty label={t('projects.filters.empty')} />
      ) : isPhone ? (
        <>
          <StatusChips items={items} active={phoneStatus} onPick={setPhoneStatus} />
          {phoneItems.length === 0 ? (
            <Empty label={t('projects.board.empty')} />
          ) : (
            <ul className="flex flex-col gap-2">
              {phoneItems.map((card) => (
                <li key={card.id}>
                  <ProjectTile card={card} onOpen={setOpen} />
                </li>
              ))}
            </ul>
          )}
        </>
      ) : mode === 'board' ? (
        <Board items={items} onOpen={setOpen} onMove={onMove} wide={device === 'monitor'} />
      ) : mode === 'table' ? (
        <Table items={items} onOpen={setOpen} />
      ) : (
        <Timeline items={items} today={today} onOpen={setOpen} />
      )}

      {open ? (
        <Sheet
          label={t('sections.projects')}
          closeLabel={t('projects.panel.close')}
          onClose={closePanel}
          wide
        >
          <ProjectPanel key={open} id={open} canEdit={canEdit} onOpen={setOpen} />
        </Sheet>
      ) : null}

      {creating ? (
        <Sheet
          label={t('projects.form.title')}
          closeLabel={t('projects.panel.close')}
          onClose={closeCreate}
        >
          <CreateProject
            today={today}
            types={view.types}
            people={view.people}
            programs={programs}
            onCancel={closeCreate}
            onCreated={(project) => {
              setCreating(false);
              setNotice(t('projects.form.created', { code: project.code }));
              setOpen(project.id);
            }}
          />
        </Sheet>
      ) : null}

      {move ? (
        <Sheet
          label={t('projects.panel.status')}
          closeLabel={t('projects.panel.close')}
          onClose={closeMove}
        >
          <StatusReason
            status={move.status}
            title={move.card.title}
            busy={status.isPending}
            onCancel={closeMove}
            onSave={(reason) =>
              status.mutate(
                { id: move.card.id, status: move.status, reason },
                { onSuccess: closeMove },
              )
            }
          />
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
  onCreate,
}: {
  view: ProjectsView;
  compact: boolean;
  total: number;
  /** `null` — телефон: у него один вид, список. */
  mode: View | null;
  onMode: (mode: View) => void;
  onCreate: (() => void) | null;
}) {
  const { t } = useTranslation();
  const demo = view.is_demo ? (
    <span title={t('pult.demoHint')}>
      <Signal state="wait">{t('pult.demo')}</Signal>
    </span>
  ) : null;

  const create = onCreate ? (
    <Button
      look="primary"
      size={compact ? 'icon' : 'base'}
      onClick={onCreate}
      aria-label={compact ? t('projects.create') : undefined}
    >
      <Plus className="size-4" aria-hidden="true" />
      {compact ? null : t('projects.create')}
    </Button>
  ) : null;

  if (compact) {
    return (
      <header className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-ink-strong">{t('sections.projects')}</h1>
          <span className="numeric min-w-0 flex-1 truncate text-xs text-ink-muted">
            {t('projects.count', { count: total })}
          </span>
          {create}
        </div>
        {demo ? <div className="flex text-xs">{demo}</div> : null}
      </header>
    );
  }

  return (
    <header className="flex flex-wrap items-center gap-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <FolderKanban className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-ink-strong">{t('sections.projects')}</h1>
          <p className="text-sm text-ink-muted">{t('sectionQuestions.projects')}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>{t('pult.asOf', { when: formatDateTime(view.as_of) })}</span>
            <span className="numeric">{t('projects.count', { count: total })}</span>
            {demo}
          </p>
        </div>
      </div>

      {mode ? (
        <span role="tablist" aria-label={t('projects.views.label')} className="inline-flex gap-1">
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
              {t(`projects.views.${each}`)}
            </button>
          ))}
        </span>
      ) : null}

      {create}
    </header>
  );
}

function Filters({
  view,
  filter,
  onFilter,
  compact,
}: {
  view: ProjectsView;
  filter: ProjectFilter;
  onFilter: (filter: ProjectFilter) => void;
  /** Телефон: поиск и два переключателя; тип и ответственный — на большом экране. */
  compact: boolean;
}) {
  const { t } = useTranslation();
  const set = (patch: Partial<ProjectFilter>) => onFilter({ ...filter, ...patch });
  const field =
    'min-h-touch rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="relative min-w-0 flex-1 basis-56">
        <span className="sr-only">{t('projects.filters.search')}</span>
        <Search
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-muted"
          aria-hidden="true"
        />
        <input
          type="search"
          value={filter.search}
          onChange={(event) => set({ search: event.target.value })}
          placeholder={t('projects.filters.search')}
          className={cn(field, 'w-full pl-8')}
        />
      </label>

      {!compact ? (
        <>
          <label>
            <span className="sr-only">{t('projects.filters.type')}</span>
            <select
              value={filter.type}
              onChange={(event) => set({ type: event.target.value })}
              className={field}
            >
              <option value="">{t('projects.filters.anyType')}</option>
              {view.types.map((type) => (
                <option key={type.code} value={type.code}>
                  {type.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">{t('projects.filters.responsible')}</span>
            <select
              value={filter.responsible}
              onChange={(event) => set({ responsible: event.target.value })}
              className={field}
            >
              <option value="">
                {t('projects.filters.responsible')}: {t('projects.filters.anyone')}
              </option>
              {view.people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </label>
        </>
      ) : null}

      <Toggle on={filter.attention} onClick={() => set({ attention: !filter.attention })}>
        {t('projects.filters.attention')}
      </Toggle>
      <Toggle on={filter.center} onClick={() => set({ center: !filter.center })}>
        {t('projects.filters.center')}
      </Toggle>

      {isFiltered(filter) ? (
        <Button look="quiet" onClick={() => onFilter(NO_FILTER)}>
          {t('projects.filters.clear')}
        </Button>
      ) : null}
    </div>
  );
}

function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        'min-h-touch rounded-[var(--radius-pill)] border px-3 text-sm',
        'transition-colors duration-[var(--motion-fast)]',
        on
          ? 'border-line-accent bg-accent-soft text-accent-ink'
          : 'border-line bg-card text-ink hover:bg-hover',
      )}
    >
      {children}
    </button>
  );
}

/** Телефон: статусы вместо колонок доски — четыре плитки в ряд. */
function StatusChips({
  items,
  active,
  onPick,
}: {
  items: ProjectCard[];
  active: ProjectStatus;
  onPick: (status: ProjectStatus) => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      role="tablist"
      aria-label={t('projects.panel.status')}
      className="grid grid-cols-4 gap-1.5"
    >
      {BOARD_COLUMNS.map((status) => {
        const count = items.filter((card) => card.status === status).length;
        return (
          <button
            key={status}
            type="button"
            role="tab"
            aria-selected={active === status}
            onClick={() => onPick(status)}
            className={cn(
              'flex min-h-touch min-w-0 flex-col items-center justify-center rounded-[var(--radius)] border px-0.5 py-1',
              active === status ? 'border-line-accent bg-accent-soft' : 'border-line bg-card',
            )}
          >
            <span className="numeric text-base leading-tight font-semibold text-ink-strong">
              {count}
            </span>
            <span className="w-full truncate text-center text-[11px] tracking-tight text-ink-muted">
              {t(`projects.statuses.${status}`)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
