/**
 * Пульт — «что требует моего внимания сейчас и какое решение я принимаю» (ТЗ 1).
 *
 * Раскладка меняется с устройством, потому что меняется задача (`app/device.ts`):
 *
 * - **телефон** — одна колонка: счётчики ступеней, лестница, под ней карточки. Первые пять
 *   строк лестницы видны без прокрутки, решение — одно касание (PLAN-10X);
 * - **ноутбук** — лестница и рядом карточки-вопросы; строка раскрывается на месте;
 * - **монитор** — три панели: лестница, раскрытая строка, карточки. Не одна широкая
 *   колонка и 85 % пустоты (аудит 20.09, В8).
 *
 * Счётчики — ещё и фильтр: касание «Горит» оставляет в лестнице только горящее. Касание
 * человека в «Кто держит» — только его строки. Показатель без действия сюда не попадает
 * (инвариант 3).
 *
 * После решения внизу на несколько секунд появляется «Отменить»: одно касание на телефоне
 * легко сделать по ошибке, и цена ошибки — запись в журнале решений.
 */

import { Gauge } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDateTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Count } from '@/shared/ui/Count';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { LadderRow, RowDetails, type RowActions, type Viewer } from './LadderRow';
import {
  LADDER,
  STEP_SIGNAL,
  rowKey,
  type DecisionKind,
  type Person,
  type PultRow,
  type PultView,
  type Step,
} from './model';
import { Orbits } from './Orbits';
import { usePult, usePultAction } from './usePult';
import { HoldersCard, MovesCard, SinceCard } from './Widgets';

/**
 * Сколько секунд держится «Отменить» после действия. Восемь, а не пять: руководитель
 * замечает ошибку, уже отведя взгляд от кнопки, и за пять секунд полоса исчезает раньше,
 * чем он к ней вернётся.
 */
const UNDO_SECONDS = 8;

/** Точка ступени. Классы полностью: имя, собранное из частей, Tailwind при сборке не найдёт. */
const DOT = { call: 'bg-call', burn: 'bg-burn', wait: 'bg-wait' } as const;

type Filter = { kind: 'step'; step: Step } | { kind: 'person'; person: Person } | null;

interface Notice {
  key: string;
  text: string;
}

export function PultSection() {
  const pult = usePult();

  if (pult.isPending) return <Loading />;
  if (pult.isError) {
    return <Failure detail={describeError(pult.error)} onRetry={() => void pult.refetch()} />;
  }
  return <Pult view={pult.data} />;
}

function Pult({ view }: { view: PultView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  const action = usePultAction();

  // Пока данные вымышленные, экран можно посмотреть глазами обоих: заказчик утверждает и
  // вид руководителя, и вид помощника. С настоящими данными вид задаёт вход по ссылке.
  const sessionViewer: Viewer = user.data?.role === 'leader' ? 'leader' : 'assistant';
  const [demoViewer, setDemoViewer] = useState<Viewer>('leader');
  const viewer = view.is_demo ? demoViewer : sessionViewer;

  const [filter, setFilter] = useState<Filter>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), UNDO_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const rows = useMemo(() => {
    if (!filter) return view.rows;
    if (filter.kind === 'step') return view.rows.filter((row) => row.step === filter.step);
    return view.rows.filter((row) => row.responsible?.id === filter.person.id);
  }, [view.rows, filter]);

  const decide = (row: Pick<PultRow, 'section' | 'entity_id' | 'title'>, kind: DecisionKind) => {
    const key = rowKey(row);
    action.mutate({ type: 'decide', key, kind });
    setNotice({
      key,
      text: t('pult.notice.decided', { what: t(`pult.decisions.${kind}`), title: row.title }),
    });
  };

  const actions: RowActions = {
    decide,
    ask: (row, text) => {
      const key = rowKey(row);
      action.mutate({ type: 'ask', key, text });
      setNotice({ key, text: t('pult.notice.asked', { title: row.title }) });
    },
  };

  const undo = () => {
    if (!notice) return;
    action.mutate({ type: 'undo', key: notice.key });
    setNotice(null);
  };

  const isPhone = device === 'phone';
  const isMonitor = device === 'monitor';
  const selected = isMonitor ? (rows.find((row) => rowKey(row) === open) ?? rows[0]) : undefined;

  const ladder = (
    <LadderCard
      rows={rows}
      onTrack={view.on_track}
      filter={filter}
      onClearFilter={() => setFilter(null)}
      asOf={view.as_of}
      viewer={viewer}
      actions={actions}
      busy={action.isPending}
      open={isMonitor ? (selected ? rowKey(selected) : null) : open}
      onToggle={(key) => setOpen(open === key && !isMonitor ? null : key)}
      detailsInline={!isMonitor}
      compact={isPhone}
    />
  );

  const widgets = (
    <>
      <SinceCard changes={view.changes} lastVisitAt={view.last_visit_at} />
      <HoldersCard
        holders={view.holders}
        active={filter?.kind === 'person' ? filter.person.id : null}
        onPick={(person) =>
          setFilter(
            filter?.kind === 'person' && filter.person.id === person.id
              ? null
              : { kind: 'person', person },
          )
        }
      />
      <MovesCard
        moves={view.deadline_moves}
        canDecide={viewer === 'leader'}
        busy={action.isPending}
        onReapprove={(item) => decide(item, 'approve')}
      />
    </>
  );

  return (
    <div className={cn('flex flex-col', isPhone ? 'gap-3' : 'gap-5')}>
      <PultHeader
        view={view}
        compact={isPhone}
        viewer={viewer}
        onViewer={view.is_demo ? setDemoViewer : undefined}
      />

      <Counters
        view={view}
        compact={isPhone}
        filter={filter}
        onFilter={(step) =>
          setFilter(filter?.kind === 'step' && filter.step === step ? null : { kind: 'step', step })
        }
      />

      {isPhone ? (
        <>
          {ladder}
          {widgets}
        </>
      ) : isMonitor ? (
        <div className="grid grid-cols-[minmax(0,5fr)_minmax(0,4fr)_minmax(0,3fr)] items-start gap-6">
          {ladder}
          <Card
            title={t('pult.detail.title')}
            className="sticky top-[calc(var(--topbar-height)+2rem)]"
          >
            {selected ? (
              <div className="flex flex-col gap-3">
                <p className="text-lg leading-snug font-semibold text-ink-strong">
                  {selected.title}
                </p>
                <RowDetails
                  row={selected}
                  viewer={viewer}
                  actions={actions}
                  busy={action.isPending}
                />
              </div>
            ) : (
              <p className="text-sm text-ink-muted">{t('pult.detail.pick')}</p>
            )}
          </Card>
          <div className="flex flex-col gap-6">{widgets}</div>
        </div>
      ) : (
        <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] items-start gap-5">
          {ladder}
          <div className="flex flex-col gap-5">{widgets}</div>
        </div>
      )}

      {notice ? <UndoNotice notice={notice} onUndo={undo} phone={isPhone} /> : null}
    </div>
  );
}

function PultHeader({
  view,
  compact,
  viewer,
  onViewer,
}: {
  view: PultView;
  /** Телефон: две короткие строки. Вопрос раздела и орбиты — на ноутбуке и мониторе. */
  compact: boolean;
  viewer: Viewer;
  onViewer: ((viewer: Viewer) => void) | undefined;
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
        <div className="flex items-baseline gap-2">
          <h1 className="text-lg font-semibold text-ink-strong">{t('sections.pult')}</h1>
          <span className="text-xs text-ink-muted">
            {t('pult.asOf', { when: formatDateTime(view.as_of) })}
          </span>
        </div>
        {demo || onViewer ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            {demo}
            {onViewer ? <ViewerSwitch viewer={viewer} onViewer={onViewer} /> : null}
          </div>
        ) : null}
      </header>
    );
  }

  return (
    <header className="flex items-center gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
            <Gauge className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-ink-strong">{t('sections.pult')}</h1>
            <p className="text-sm text-ink-muted">{t('sectionQuestions.pult')}</p>
          </div>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <span>{t('pult.asOf', { when: formatDateTime(view.as_of) })}</span>
          {demo}
          {onViewer ? <ViewerSwitch viewer={viewer} onViewer={onViewer} /> : null}
        </div>
      </div>

      <Orbits className="h-24 w-48 shrink-0" />
    </header>
  );
}

function ViewerSwitch({ viewer, onViewer }: { viewer: Viewer; onViewer: (v: Viewer) => void }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1" role="group" aria-label={t('pult.viewAs')}>
      <span className="mr-1">{t('pult.viewAs')}</span>
      {(['leader', 'assistant'] as const).map((each) => (
        <button
          key={each}
          type="button"
          aria-pressed={viewer === each}
          onClick={() => onViewer(each)}
          className={cn(
            'min-h-touch rounded-[var(--radius-pill)] border px-3 text-xs font-medium',
            'transition-colors duration-[var(--motion-fast)]',
            viewer === each
              ? 'border-accent bg-accent text-ink-inverse'
              : 'border-line bg-card text-ink hover:bg-hover',
          )}
        >
          {t(`role.${each}`)}
        </button>
      ))}
    </span>
  );
}

function Counters({
  view,
  compact,
  filter,
  onFilter,
}: {
  view: PultView;
  /** Телефон: шесть плиток в один ряд — два ряда съедали место пяти строк лестницы. */
  compact: boolean;
  filter: Filter;
  onFilter: (step: Step) => void;
}) {
  const { t } = useTranslation();
  // Старейшее ожидание — первая строка ступени: порядок строк задаёт сервер (ТЗ 4).
  const oldest = view.rows.find((row) => row.step === 'awaiting_decision');

  if (compact) {
    const tile =
      'flex h-full min-h-touch w-full flex-col items-center justify-center rounded-[var(--radius)] border px-1 py-1.5';
    return (
      <nav aria-label={t('pult.counters.title')}>
        <ul className="grid grid-cols-6 gap-1.5">
          {LADDER.map((step) => {
            const active = filter?.kind === 'step' && filter.step === step;
            const count = view.counts[step];
            return (
              <li key={step} className="min-w-0">
                <button
                  type="button"
                  onClick={() => onFilter(step)}
                  aria-pressed={active}
                  aria-label={t('pult.counters.filter', { step: t(`pult.steps.${step}`) })}
                  className={cn(
                    tile,
                    active ? 'border-line-accent bg-accent-soft' : 'border-line bg-card',
                  )}
                >
                  <span className="flex items-center gap-1">
                    <span
                      className={cn('size-1.5 rounded-full', DOT[STEP_SIGNAL[step]])}
                      aria-hidden="true"
                    />
                    <Count
                      value={count}
                      className={cn(
                        'text-lg leading-tight font-semibold',
                        count > 0 ? 'text-ink-strong' : 'text-ink-muted',
                      )}
                    />
                  </span>
                  <span className="w-full truncate text-center text-[11px] text-ink-muted">
                    {t(`pult.stepsShort.${step}`)}
                  </span>
                </button>
              </li>
            );
          })}
          <li className="min-w-0">
            <div className={cn(tile, 'border-line bg-sunken')}>
              <Count
                value={view.on_track}
                className="text-lg leading-tight font-semibold text-ink"
              />
              <span className="w-full truncate text-center text-[11px] text-ink-muted">
                {t('pult.stepsShort.on_track')}
              </span>
            </div>
          </li>
        </ul>
      </nav>
    );
  }

  return (
    <nav aria-label={t('pult.counters.title')}>
      <ul className="grid grid-cols-3 gap-2 lg:grid-cols-6">
        {LADDER.map((step) => {
          const active = filter?.kind === 'step' && filter.step === step;
          const count = view.counts[step];
          return (
            <li key={step} className="min-w-0">
              <button
                type="button"
                onClick={() => onFilter(step)}
                aria-pressed={active}
                aria-label={t('pult.counters.filter', { step: t(`pult.steps.${step}`) })}
                className={cn(
                  'flex h-full min-h-touch w-full flex-col items-start rounded-[var(--radius)] border px-3 py-2 text-left',
                  'transition-colors duration-[var(--motion-fast)] hover:bg-hover',
                  active ? 'border-line-accent bg-accent-soft' : 'border-line bg-card',
                )}
              >
                <span className="flex items-center gap-1.5 text-xs text-ink-muted">
                  <span
                    className={cn('size-1.5 rounded-full', DOT[STEP_SIGNAL[step]])}
                    aria-hidden="true"
                  />
                  <span className="truncate">{t(`pult.steps.${step}`)}</span>
                </span>
                <Count
                  value={count}
                  className={cn(
                    'text-2xl leading-tight font-semibold',
                    count > 0 ? 'text-ink-strong' : 'text-ink-muted',
                  )}
                />
                {step === 'awaiting_decision' && oldest ? (
                  <span className="text-[11px] leading-tight text-call-ink">
                    {t('pult.counters.oldest', { days: oldest.deviation })}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
        <li className="min-w-0">
          <div className="flex h-full min-h-touch flex-col items-start rounded-[var(--radius)] border border-line bg-sunken px-3 py-2">
            <span className="flex items-center gap-1.5 text-xs text-ink-muted">
              <span className="size-1.5 rounded-full bg-calm" aria-hidden="true" />
              {t('pult.counters.onTrack')}
            </span>
            <Count
              value={view.on_track}
              className="text-2xl leading-tight font-semibold text-ink"
            />
          </div>
        </li>
      </ul>
    </nav>
  );
}

function LadderCard({
  rows,
  onTrack,
  filter,
  onClearFilter,
  asOf,
  viewer,
  actions,
  busy,
  open,
  onToggle,
  detailsInline,
  compact,
}: {
  rows: PultRow[];
  onTrack: number;
  filter: Filter;
  onClearFilter: () => void;
  asOf: string;
  viewer: Viewer;
  actions: RowActions;
  busy: boolean;
  open: string | null;
  onToggle: (key: string) => void;
  detailsInline: boolean;
  /**
   * Телефон: лестница без рамки карточки. Заголовок и вопрос карточки повторяли бы вопрос
   * раздела из шапки и стоили бы строки лестницы.
   */
  compact: boolean;
}) {
  const { t } = useTranslation();
  const filterLabel = filter
    ? filter.kind === 'step'
      ? t(`pult.steps.${filter.step}`)
      : filter.person.name
    : null;

  const body = (
    <>
      {filterLabel ? (
        <div className="mb-2 flex items-center gap-2">
          <p className="min-w-0 flex-1 truncate text-sm text-ink-muted">
            {t('pult.ladder.filtered', { what: filterLabel })}
          </p>
          {compact ? (
            <Button look="quiet" onClick={onClearFilter}>
              {t('pult.ladder.showAll')}
            </Button>
          ) : null}
        </div>
      ) : null}

      {rows.length === 0 ? (
        <p className="py-4 text-sm text-calm-ink">{t('pult.ladder.allClear')}</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {rows.map((row) => {
            const key = rowKey(row);
            return (
              <LadderRow
                key={key}
                row={row}
                viewer={viewer}
                actions={actions}
                busy={busy}
                expanded={detailsInline && open === key}
                selected={!detailsInline && open === key}
                onToggle={() => onToggle(key)}
                detailsInline={detailsInline}
                compact={compact}
              />
            );
          })}
        </ol>
      )}

      {!filter ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-calm-ink">
          <span className="size-1.5 rounded-full bg-calm" aria-hidden="true" />
          {t('pult.ladder.onTrack', { count: onTrack })}
        </p>
      ) : null}
    </>
  );

  if (compact) {
    return (
      <section aria-label={t('pult.ladder.title')} className="min-w-0">
        {body}
      </section>
    );
  }

  return (
    <Card
      title={t('pult.ladder.title')}
      question={t('pult.ladder.question')}
      freshness={t('pult.asOf', { when: formatDateTime(asOf) })}
      action={
        filterLabel ? (
          <Button look="quiet" onClick={onClearFilter}>
            {t('pult.ladder.showAll')}
          </Button>
        ) : undefined
      }
    >
      {body}
    </Card>
  );
}

function UndoNotice({
  notice,
  onUndo,
  phone,
}: {
  notice: Notice;
  onUndo: () => void;
  phone: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'fixed inset-x-4 z-50 mx-auto flex max-w-xl items-center gap-3 rounded-[var(--radius-lg)]',
        'border border-line bg-raised px-4 py-2 shadow-raised',
        // На телефоне — над нижней панелью и жест-полосой, иначе кнопку не нажать.
        phone ? 'bottom-[calc(env(safe-area-inset-bottom)+4.75rem)]' : 'bottom-6',
      )}
    >
      <p className="min-w-0 flex-1 truncate text-sm text-ink">{notice.text}</p>
      <Button look="quiet" onClick={onUndo}>
        {t('pult.notice.undo')}
      </Button>
    </div>
  );
}
