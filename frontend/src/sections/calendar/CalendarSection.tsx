/**
 * Календарь — «что и когда наступит, где тесно» (ТЗ 2).
 *
 * Раскладка меняется с устройством (`app/device.ts`):
 *
 * - **телефон** — «где неделя перегружена?» и ближайшие две недели списком по дням; сетки
 *   месяца нет (ТЗ 6: без тяжёлой графики);
 * - **ноутбук и монитор** — месяц сеткой, рядом горячие дни и выбранный день; на мониторе
 *   клетки шире и колонка шире.
 *
 * Годовой цикл заводит помощник кнопкой в шапке; там же — список всех циклов. Касание даты
 * цикла открывает его правило и даты на год вперёд. Касание остального открывает карточку
 * записи в её разделе листом поверх календаря: проект (и веха — своим проектом) или задачу.
 * Решение руководителя открывает свой лист — что решено, кто и к какому сроку исполняет, — а
 * оттуда карточку того, по чему оно принято.
 */

import { useNavigate } from '@tanstack/react-router';
import { CalendarDays, Plus, Repeat } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { ProjectPanel } from '@/sections/projects/ProjectPanel';
import { TaskPanel } from '@/sections/tasks/TaskPanel';
import { useTasks } from '@/sections/tasks/useTasks';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDateTime, localDay } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Sheet } from '@/shared/ui/Sheet';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { CycleForm } from './CycleForm';
import { CyclePanel } from './CyclePanel';
import { CyclesList } from './CyclesList';
import { DayAgenda } from './DayAgenda';
import { DecisionPanel } from './DecisionPanel';
import { addDays, addMonths, monthRange } from './grid';
import { HotDaysCard } from './HotDaysCard';
import { KINDS, type CalendarItem, type CalendarView, type ItemKind } from './model';
import { MonthGrid } from './MonthGrid';
import { SourceFilter } from './SourceFilter';
import { dayAnchor } from './kinds';
import { isShown } from './text';
import { Upcoming } from './Upcoming';
import { useCalendar } from './useCalendar';

/** Сколько дней в списке телефона сразу и сколько добавляет «ещё». */
const PHONE_DAYS = 14;

/** Сколько секунд видна подсказка. */
const NOTICE_SECONDS = 8;

const DAY_MS = 86_400_000;

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}

export function CalendarSection() {
  const device = useDevice();
  // «Сегодня» до первого ответа — по часам устройства в Ташкенте, дальше — день сервера:
  // вкладка, открытая через полночь, иначе держала бы вчерашний день в начале списка, и
  // вчерашнее стояло бы в нём и в «срок прошёл» сразу.
  const [today, setToday] = useState(() => ({ day: localDay(new Date()), at: 0 }));
  const [month, setMonth] = useState(today.day.slice(0, 7));
  const [days, setDays] = useState(PHONE_DAYS);
  const isPhone = device === 'phone';

  const range = isPhone ? { from: today.day, to: addDays(today.day, days - 1) } : monthRange(month);
  const calendar = useCalendar(range);

  // День сервера берётся только из ответа свежее последней смены дня. Смена дня меняет
  // диапазон списка, а под прежним диапазоном в кэше может лежать ответ с другим днём: если
  // часы телефона спешат, два диапазона отдавали бы друг другу разные дни без конца.
  const { data, dataUpdatedAt, isPlaceholderData } = calendar;
  useEffect(() => {
    if (!data || isPlaceholderData || dataUpdatedAt <= today.at) return;
    const day = localDay(data.as_of);
    if (day !== today.day) setToday({ day, at: dataUpdatedAt });
  }, [data, dataUpdatedAt, isPlaceholderData, today]);

  if (calendar.isPending) return <Loading />;
  if (calendar.isError) {
    return (
      <Failure detail={describeError(calendar.error)} onRetry={() => void calendar.refetch()} />
    );
  }
  return (
    <Calendar
      view={calendar.data}
      stale={calendar.isPlaceholderData}
      month={month}
      onMonth={setMonth}
      onMoreDays={() => setDays(days + PHONE_DAYS)}
      onReach={(date) => {
        // Горячий день за концом списка: список растёт целыми двумя неделями до него.
        const needed = daysBetween(today.day, date) + 1;
        if (needed > days) setDays(Math.ceil(needed / PHONE_DAYS) * PHONE_DAYS);
      }}
    />
  );
}

function Calendar({
  view,
  stale,
  month,
  onMonth,
  onMoreDays,
  onReach,
}: {
  view: CalendarView;
  stale: boolean;
  month: string;
  onMonth: (month: string) => void;
  onMoreDays: () => void;
  onReach: (date: string) => void;
}) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  const canEdit = user.data?.role !== 'leader';
  const isPhone = device === 'phone';
  const today = localDay(view.as_of);

  const [shown, setShown] = useState<ReadonlySet<ItemKind>>(() => new Set(KINDS));
  const [selected, setSelected] = useState(today);
  const [cycle, setCycle] = useState<string | null>(null);
  const [listing, setListing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const navigate = useNavigate();
  const [card, setCard] = useState<{ kind: 'project' | 'task'; id: string } | null>(null);
  const [decision, setDecision] = useState<CalendarItem | null>(null);
  /** День, к которому прокрутить список телефона, когда он дорисуется. */
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), NOTICE_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const items = useMemo(
    () => view.items.filter((item) => isShown(item, shown)),
    [view.items, shown],
  );
  const hidden = useMemo(() => {
    const byDay = new Map<string, number>();
    for (const item of view.items) {
      if (!isShown(item, shown)) byDay.set(item.date, (byDay.get(item.date) ?? 0) + 1);
    }
    return byDay;
  }, [view.items, shown]);
  const overdue = useMemo(
    () => view.overdue.filter((item) => isShown(item, shown)),
    [view.overdue, shown],
  );

  useEffect(() => {
    if (!target) return;
    const found = document.getElementById(dayAnchor(target));
    if (!found) return;
    found.scrollIntoView?.({ block: 'start' });
    setTarget(null);
  }, [target, view.items]);

  const toggle = (kind: ItemKind) => {
    const next = new Set(shown);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    setShown(next);
  };
  const showAll = () => setShown(new Set(KINDS));

  const first = addMonths(today.slice(0, 7), -1);
  const last = view.horizon_to.slice(0, 7);

  // Листание месяца уводит и выбранный день: иначе справа стоял бы день из другого месяца
  // со «сроков нет», хотя его сроки просто не в этом месяце.
  const goMonth = (next: string) => {
    onMonth(next);
    setSelected(today.slice(0, 7) === next ? today : `${next}-01`);
  };

  // Горячий день из карточки: на сетке — его месяц и день, в списке телефона — прокрутка,
  // и если день за концом списка — сначала список дорастает до него.
  const pick = (date: string) => {
    if (isPhone) {
      if (date > view.range.to) onReach(date);
      setTarget(date);
      return;
    }
    onMonth(date.slice(0, 7));
    setSelected(date);
  };

  // Касание даты: цикл — его лист, решение — свой лист, проект и задача — их карточка;
  // поручение Ижро и подготовка — их раздел с открытой карточкой.
  const open = (item: CalendarItem) => {
    const { kind, id } = item.target;
    if (kind === 'cycle') setCycle(id);
    else if (kind === 'ijro')
      void navigate({ to: '/ijro', search: { view: 'assignments', open: id } });
    else if (kind === 'preparation') void navigate({ to: '/reports', search: { open: id } });
    else if (item.kind === 'decision' || kind === 'decision') setDecision(item);
    else setCard({ kind, id });
  };

  const closeCycle = useCallback(() => setCycle(null), []);
  const closeCard = useCallback(() => setCard(null), []);
  const closeDecision = useCallback(() => setDecision(null), []);
  const closeList = useCallback(() => setListing(false), []);
  const closeCreate = useCallback(() => setCreating(false), []);

  const hotCard = (
    <HotDaysCard
      hot={view.hot_ahead}
      windowDays={view.hot_window_days}
      threshold={view.hot_threshold}
      today={today}
      asOf={view.as_of}
      onPick={pick}
    />
  );

  // Пока грузится новый месяц, виден прежний: выбранного дня в нём может не быть, и
  // «сроков нет» было бы неправдой — день приглушён, а не пуст.
  const selectedLoaded = selected >= view.range.from && selected <= view.range.to;

  return (
    <div className={cn('flex flex-col', isPhone ? 'gap-3' : 'gap-5')}>
      <Header
        view={view}
        compact={isPhone}
        onList={() => setListing(true)}
        onCreate={canEdit ? () => setCreating(true) : null}
      />

      {isPhone ? (
        <>
          {hotCard}
          <SourceFilter shown={shown} onToggle={toggle} />
          <Upcoming
            items={items}
            hidden={hidden}
            overdue={overdue}
            hot={view.hot_days}
            today={today}
            onOpen={open}
            onShowAll={showAll}
            onMore={view.range.to < view.horizon_to ? onMoreDays : null}
          />
        </>
      ) : (
        <>
          <SourceFilter shown={shown} onToggle={toggle} />
          <div
            className={cn(
              'grid items-start gap-5',
              device === 'monitor'
                ? 'grid-cols-[minmax(0,1fr)_28rem]'
                : 'grid-cols-[minmax(0,1fr)_22rem]',
            )}
          >
            <MonthGrid
              month={month}
              range={view.range}
              items={items}
              hidden={hidden}
              hot={view.hot_days}
              today={today}
              selected={selected}
              canBack={month > first}
              canForward={month < last}
              onMonth={(step) => goMonth(addMonths(month, step))}
              onToday={() => {
                onMonth(today.slice(0, 7));
                setSelected(today);
              }}
              onSelect={setSelected}
              tall={device === 'monitor'}
              stale={stale}
            />
            <div className="flex min-w-0 flex-col gap-5">
              {hotCard}
              <DayAgenda
                date={selected}
                today={today}
                items={items.filter((item) => item.date === selected)}
                hidden={selectedLoaded ? (hidden.get(selected) ?? 0) : 0}
                hot={view.hot_days.find((day) => day.date === selected)}
                overdue={overdue}
                stale={stale || !selectedLoaded}
                onOpen={open}
                onShowAll={showAll}
              />
            </div>
          </div>
        </>
      )}

      {decision ? (
        <Sheet
          label={t('calendar.decision.label')}
          closeLabel={t('calendar.decision.close')}
          onClose={closeDecision}
        >
          <DecisionPanel
            item={decision}
            onOpen={(target) => {
              setDecision(null);
              setCard(target);
            }}
          />
        </Sheet>
      ) : null}

      {card?.kind === 'project' ? (
        <Sheet
          label={t('sections.projects')}
          closeLabel={t('projects.panel.close')}
          onClose={closeCard}
          wide
        >
          <ProjectPanel
            key={card.id}
            id={card.id}
            canEdit={canEdit}
            onOpen={(id) => setCard({ kind: 'project', id })}
          />
        </Sheet>
      ) : null}

      {card?.kind === 'task' ? (
        <Sheet
          label={t('sections.tasks')}
          closeLabel={t('tasks.panel.close')}
          onClose={closeCard}
          wide
        >
          <TaskCard key={card.id} id={card.id} canEdit={canEdit} />
        </Sheet>
      ) : null}

      {listing ? (
        <Sheet
          label={t('calendar.cycles.title')}
          closeLabel={t('calendar.cycles.close')}
          onClose={closeList}
        >
          <CyclesList
            onOpen={(id) => {
              setListing(false);
              setCycle(id);
            }}
          />
        </Sheet>
      ) : null}

      {cycle ? (
        <Sheet
          label={t('calendar.kinds.cycle')}
          closeLabel={t('calendar.cycle.close')}
          onClose={closeCycle}
        >
          <CyclePanel
            key={cycle}
            id={cycle}
            canEdit={canEdit}
            onCancelled={() => {
              setCycle(null);
              setNotice(t('calendar.cycle.cancelled'));
            }}
          />
        </Sheet>
      ) : null}

      {creating ? (
        <Sheet
          label={t('calendar.form.title')}
          closeLabel={t('calendar.form.cancel')}
          onClose={closeCreate}
        >
          <CycleForm
            year={Number(today.slice(0, 4))}
            people={view.people}
            projects={view.projects}
            onCancel={closeCreate}
            onCreated={(created) => {
              setCreating(false);
              setNotice(t('calendar.form.created', { title: created.title }));
              setCycle(created.id);
            }}
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

/**
 * Карточка задачи — та же, что в разделе «Задачи»; её справочники (типы, люди, проекты)
 * — из ответа того раздела, чтобы правка из календаря шла по тем же правилам.
 */
function TaskCard({ id, canEdit }: { id: string; canEdit: boolean }) {
  const tasks = useTasks();
  if (tasks.isPending) return <Loading />;
  if (tasks.isError) {
    return <Failure detail={describeError(tasks.error)} onRetry={() => void tasks.refetch()} />;
  }
  return (
    <TaskPanel
      id={id}
      canEdit={canEdit}
      types={tasks.data.types}
      people={tasks.data.people}
      projects={tasks.data.projects}
    />
  );
}

function Header({
  view,
  compact,
  onList,
  onCreate,
}: {
  view: CalendarView;
  compact: boolean;
  onList: () => void;
  onCreate: (() => void) | null;
}) {
  const { t } = useTranslation();
  const demo = view.is_demo ? (
    <span title={t('pult.demoHint')}>
      <Signal state="wait">{t('pult.demo')}</Signal>
    </span>
  ) : null;

  const list = (
    <Button
      size={compact ? 'icon' : 'base'}
      onClick={onList}
      aria-label={compact ? t('calendar.cycles.open') : undefined}
    >
      <Repeat className="size-4" aria-hidden="true" />
      {compact ? null : t('calendar.cycles.open')}
    </Button>
  );

  const create = onCreate ? (
    <Button
      look="primary"
      size={compact ? 'icon' : 'base'}
      onClick={onCreate}
      aria-label={compact ? t('calendar.create') : undefined}
    >
      <Plus className="size-4" aria-hidden="true" />
      {compact ? null : t('calendar.create')}
    </Button>
  ) : null;

  if (compact) {
    return (
      <header className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <h1 className="min-w-0 flex-1 text-lg font-semibold text-ink-strong">
            {t('sections.calendar')}
          </h1>
          {list}
          {create}
        </div>
        <p className="text-sm text-ink-muted">{t('sectionQuestions.calendar')}</p>
        {demo ? <div className="flex text-xs">{demo}</div> : null}
      </header>
    );
  }

  return (
    <header className="flex flex-wrap items-center gap-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <CalendarDays className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-ink-strong">{t('sections.calendar')}</h1>
          <p className="text-sm text-ink-muted">{t('sectionQuestions.calendar')}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>{t('pult.asOf', { when: formatDateTime(view.as_of) })}</span>
            {demo}
          </p>
        </div>
      </div>
      <span className="flex flex-wrap gap-2">
        {list}
        {create}
      </span>
    </header>
  );
}
