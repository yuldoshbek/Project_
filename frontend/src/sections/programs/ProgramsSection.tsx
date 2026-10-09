/**
 * Программы — «где мы по многолетним программам и что должно случиться до конца года»
 * (ТЗ 2).
 *
 * Раскладка меняется с устройством (`app/device.ts`):
 *
 * - **телефон** — плитки программ с отсчётом и вехами по годам; горизонта-шкалы нет
 *   (ТЗ 6: без диаграммы Ганта); под ними «успеваем?» и «до конца года»;
 * - **ноутбук** — горизонт лет во всю ширину, под ним две карточки-вопроса рядом;
 * - **монитор** — горизонт с раскрытыми подпроектами и колонка вопросов рядом: не одна
 *   широкая полоса и пустота (аудит 20.09, В8).
 *
 * Раздел только читает. Программу правят в карточке проекта; касание открывает карточку
 * программы, а её действия — «перенести дату», «урезать объём» — открывают карточку проекта
 * из «Проектов» на нужном блоке: вторая форма правки той же записи разошлась бы с первой.
 */

import { Layers } from 'lucide-react';
import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { ProjectPanel, type PanelFocus } from '@/sections/projects/ProjectPanel';
import { describeError } from '@/shared/api/client';
import { useStatuses } from '@/shared/api/statuses';
import { cn } from '@/shared/lib/cn';
import { formatDate, formatDateTime, localDay } from '@/shared/time';
import { Sheet } from '@/shared/ui/Sheet';
import { Empty, Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';
import { useLinkedOpen } from '@/shared/lib/useLinkedOpen';

import { Horizon } from './Horizon';
import { TERMINAL, type ProgramCard, type ProgramsView } from './model';
import { PaceCard } from './PaceCard';
import { ProgramPanel, type PanelAction } from './ProgramPanel';
import { ProgramTile } from './ProgramTile';
import { usePrograms } from './usePrograms';
import { YearEndCard } from './YearEndCard';

/** Действие карточки программы → блок карточки проекта, с которого её открыть. */
const FOCUS: Record<PanelAction, PanelFocus | undefined> = {
  move: 'whatif',
  cut: 'milestones',
  card: undefined,
};

export function ProgramsSection() {
  const programs = usePrograms();
  if (programs.isPending) return <Loading />;
  if (programs.isError) {
    return (
      <Failure detail={describeError(programs.error)} onRetry={() => void programs.refetch()} />
    );
  }
  return <Programs view={programs.data} />;
}

function Programs({ view }: { view: ProgramsView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const isPhone = device === 'phone';
  const isMonitor = device === 'monitor';
  const today = localDay(view.as_of);
  const user = useCurrentUser();
  // Вносит данные помощник, руководитель смотрит и считает «что если» (ТЗ 1).
  const canEdit = user.data?.role !== 'leader';

  // Карточка из ссылки — так её открывает поиск.
  const [open, setOpen] = useLinkedOpen();
  const [project, setProject] = useState<{ id: string; focus: PanelFocus | undefined } | null>(
    null,
  );

  const active = view.items.filter((card) => !TERMINAL.has(card.status));
  const closed = view.items.filter((card) => TERMINAL.has(card.status));
  const opened = view.items.find((card) => card.id === open) ?? null;
  const closePanel = useCallback(() => setOpen(null), [setOpen]);
  const closeProject = useCallback(() => setProject(null), [setProject]);

  // Карточка проекта сменяет карточку программы, а не ложится вторым листом поверх.
  const onAction = (id: string, action: PanelAction) => {
    setOpen(null);
    setProject({ id, focus: FOCUS[action] });
  };

  const yearEnd = (
    <YearEndCard
      rows={view.year_end}
      year={Number(today.slice(0, 4))}
      asOf={view.as_of}
      onOpen={setOpen}
    />
  );
  const pace = <PaceCard items={active} asOf={view.as_of} onOpen={setOpen} onAction={onAction} />;
  const closedList = <ClosedList items={closed} onOpen={setOpen} />;

  return (
    <div className={cn('flex flex-col', isPhone ? 'gap-3' : 'gap-5')}>
      <Header view={view} compact={isPhone} total={active.length} />

      {active.length === 0 ? (
        <Empty label={t('programs.empty')} />
      ) : isPhone ? (
        <>
          <ul className="flex flex-col gap-2">
            {active.map((card) => (
              <li key={card.id}>
                <ProgramTile card={card} horizon={view.horizon} onOpen={setOpen} />
              </li>
            ))}
          </ul>
          {closedList}
          {pace}
          {yearEnd}
        </>
      ) : isMonitor ? (
        <div className="grid grid-cols-[minmax(0,1fr)_26rem] items-start gap-6">
          {/* Колонка вопросов — постоянной ширины, остальное — горизонту: оболочка ограничивает
              ширину, и доля 2:1 давала шкале на мониторе меньше места, чем на ноутбуке. */}
          <div className="flex min-w-0 flex-col gap-4">
            <Horizon
              items={active}
              horizon={view.horizon}
              today={today}
              expanded
              onOpen={setOpen}
            />
            {closedList}
          </div>
          {/* «Успеваем?» — первым: карточка короткая, а «не успевают» — то, ради чего смотрят
              обзор. Длинный список «до конца года» под ней иначе уводил её за край экрана. */}
          <div className="flex min-w-0 flex-col gap-6">
            {pace}
            {yearEnd}
          </div>
        </div>
      ) : (
        <>
          <Horizon
            items={active}
            horizon={view.horizon}
            today={today}
            expanded={false}
            onOpen={setOpen}
          />
          {closedList}
          <div className="grid grid-cols-2 items-start gap-5">
            {yearEnd}
            {pace}
          </div>
        </>
      )}

      {opened ? (
        <Sheet
          label={t('sections.programs')}
          closeLabel={t('programs.panel.close')}
          onClose={closePanel}
          wide
        >
          <ProgramPanel card={opened} horizon={view.horizon} onAction={onAction} />
        </Sheet>
      ) : null}

      {project ? (
        <Sheet
          label={t('sections.projects')}
          closeLabel={t('projects.panel.close')}
          onClose={closeProject}
          wide
        >
          <ProjectPanel
            key={project.id}
            id={project.id}
            canEdit={canEdit}
            focus={project.focus}
            onOpen={(id) => setProject({ id, focus: undefined })}
          />
        </Sheet>
      ) : null}
    </div>
  );
}

function Header({ view, compact, total }: { view: ProgramsView; compact: boolean; total: number }) {
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
          <h1 className="text-lg font-semibold text-ink-strong">{t('sections.programs')}</h1>
          <span className="numeric min-w-0 flex-1 truncate text-xs text-ink-muted">
            {t('programs.count', { count: total })}
          </span>
        </div>
        <p className="text-sm text-ink-muted">{t('sectionQuestions.programs')}</p>
        {demo ? <div className="flex text-xs">{demo}</div> : null}
      </header>
    );
  }

  return (
    <header className="flex flex-wrap items-center gap-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <Layers className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-ink-strong">{t('sections.programs')}</h1>
          <p className="text-sm text-ink-muted">{t('sectionQuestions.programs')}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>{t('pult.asOf', { when: formatDateTime(view.as_of) })}</span>
            <span className="numeric">{t('programs.count', { count: total })}</span>
            {demo}
          </p>
        </div>
      </div>
    </header>
  );
}

/** Завершённые и отменённые — свёрнуты: раздел про то, что впереди. */
function ClosedList({ items, onOpen }: { items: ProgramCard[]; onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const statuses = useStatuses('project_statuses');
  const [shown, setShown] = useState(false);
  if (items.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        aria-expanded={shown}
        onClick={() => setShown(!shown)}
        className="min-h-touch self-start rounded-[var(--radius)] px-2 text-sm text-accent-ink hover:bg-hover"
      >
        {shown ? t('programs.closed.hide') : t('programs.closed.show', { count: items.length })}
      </button>
      {shown ? (
        <ul className="flex flex-col gap-1">
          {items.map((card) => (
            <li key={card.id}>
              <button
                type="button"
                onClick={() => onOpen(card.id)}
                className="flex min-h-touch w-full min-w-0 items-baseline gap-2 rounded-[var(--radius)] border border-line bg-sunken px-3 py-2 text-left hover:bg-hover"
              >
                <span className="min-w-0 flex-1 truncate text-sm text-ink-strong">
                  {card.title}
                </span>
                <span className="numeric shrink-0 text-xs text-ink-muted">
                  {[
                    statuses.name(card.status),
                    t('programs.closed.endedOn', { date: formatDate(card.due_on) }),
                  ].join(' · ')}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
