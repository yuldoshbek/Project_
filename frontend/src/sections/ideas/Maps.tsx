/**
 * Карты: список, полотно на ноутбуке, контур на телефоне (ТЗ 6, 11).
 *
 * Полотно — узлы-кнопки на прокручиваемой плоскости и линии «родитель — потомок» под ними;
 * узел перетаскивается мышью или пальцем, а с клавиатуры — стрелками, по 20 px. Графической
 * библиотеки нет: узлов десятки, а не тысячи, и прямоугольник с линией не стоит лишней
 * сотни килобайт на телефоне руководителя. На мониторе карта только смотрится — правки там
 * нет (ТЗ 6); на телефоне — контур, полотна нет.
 *
 * В режиме «Структура» узел показывает связанную запись и её ступень Пульта, а узел без
 * связи — пунктиром: в этом режиме узлы и есть проекты и задачи (CONTEXT).
 */

import { ArrowLeft, Plus } from 'lucide-react';
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { STEP_SIGNAL } from '@/sections/pult/model';
import { ApiError, describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Empty, Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import {
  MAP_MODES,
  NODE_HEIGHT,
  NODE_WIDTH,
  type IdeasView,
  type MapCard,
  type MapMode,
  type MapNode,
} from './model';
import { branchStamp } from './stamp';
import { descendants } from './text';
import {
  useAddNode,
  useConvertNode,
  useCreateMap,
  useDeleteNode,
  useEditMap,
  useEditNode,
  useMap,
  useMoveNode,
  useSetParent,
} from './useIdeas';

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

/** Шаг стрелки с клавиатуры и порог, после которого касание — перетаскивание, а не выбор. */
const KEY_STEP = 20;
const DRAG_THRESHOLD = 4;
const MARGIN = 40;

/** Мельче карта не вписывается: подпись узла в 0,6 ещё читается, дальше — прокрутка. */
const MIN_SCALE = 0.6;

export function Maps({
  view,
  openId,
  onOpen,
}: {
  view: IdeasView;
  openId: string | null;
  onOpen: (id: string | null) => void;
}) {
  const { t } = useTranslation();
  const device = useDevice();
  if (openId) return <MapScreen id={openId} onBack={() => onOpen(null)} />;
  return (
    <div className="flex flex-col gap-4">
      {device === 'monitor' ? null : <NewMap onCreated={onOpen} />}
      {view.maps.length === 0 ? (
        <Empty label={t('ideas.maps.empty')} />
      ) : (
        <ul
          aria-label={t('ideas.maps.label')}
          className={cn(
            'grid gap-2',
            device === 'phone' ? 'grid-cols-1' : 'grid-cols-2 gap-3',
            device === 'monitor' && 'grid-cols-3 gap-4',
          )}
        >
          {view.maps.map((each) => (
            <li
              key={each.id}
              className="min-w-0 rounded-[var(--radius-lg)] border border-line bg-card"
            >
              <button
                type="button"
                onClick={() => onOpen(each.id)}
                className="flex min-h-touch w-full flex-col gap-1 p-4 text-left"
              >
                <span className="inline-flex items-center gap-2">
                  <Signal state={each.mode === 'structure' ? 'calm' : 'plain'}>
                    {t(`ideas.modes.${each.mode}`)}
                  </Signal>
                  <span className="numeric text-xs text-ink-muted">
                    {formatDate(each.changed_at)}
                  </span>
                </span>
                <span className="font-semibold text-ink-strong">{each.title}</span>
                <span className="text-sm text-ink-muted">
                  {t('ideas.maps.counts', { count: each.nodes, linked: each.linked })}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NewMap({ onCreated }: { onCreated: (id: string) => void }) {
  const { t } = useTranslation();
  const create = useCreateMap();
  const [title, setTitle] = useState('');
  return (
    <Card title={t('ideas.maps.new')} question={t('ideas.maps.newHint')}>
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (!title.trim()) return;
          create.mutate(
            { title, mode: 'sketch' },
            {
              onSuccess: (created) => {
                setTitle('');
                onCreated(created.id);
              },
            },
          );
        }}
      >
        <input
          aria-label={t('ideas.maps.title')}
          placeholder={t('ideas.maps.title')}
          className={cn(FIELD, 'flex-1')}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <Button type="submit" look="primary" disabled={create.isPending || !title.trim()}>
          <Plus className="size-4" aria-hidden="true" />
          {t('ideas.maps.create')}
        </Button>
      </form>
    </Card>
  );
}

function MapScreen({ id, onBack }: { id: string; onBack: () => void }) {
  const { t } = useTranslation();
  const device = useDevice();
  const board = useMap(id);
  if (board.isPending) return <Loading />;
  // Сбой фонового опроса не прячет полотно: неудачный повтор оставляет прежние данные, а с
  // полотном ушли бы выбор узла и недописанная подпись.
  if (!board.data) {
    return <Failure detail={describeError(board.error)} onRetry={() => void board.refetch()} />;
  }
  const editable = device === 'laptop';
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="small" look="quiet" onClick={onBack}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t('ideas.maps.back')}
        </Button>
        <h2 className="order-last w-full min-w-0 text-lg font-semibold text-ink-strong sm:order-none sm:w-auto sm:flex-1">
          {board.data.title}
        </h2>
        {editable ? (
          <ModeSwitch board={board.data} />
        ) : (
          <Signal state={board.data.mode === 'structure' ? 'calm' : 'plain'}>
            {t(`ideas.modes.${board.data.mode}`)}
          </Signal>
        )}
      </div>
      <p className="text-sm text-ink-muted">{t(`ideas.modes.${board.data.mode}Hint`)}</p>
      {board.isError ? (
        <p role="status" className="text-sm text-wait-ink">
          {t('ideas.canvas.stale', { detail: describeError(board.error) })}
        </p>
      ) : null}
      {device === 'phone' ? (
        <Outline board={board.data} />
      ) : (
        <Board board={board.data} editable={editable} />
      )}
    </div>
  );
}

function ModeSwitch({ board }: { board: MapCard }) {
  const { t } = useTranslation();
  const edit = useEditMap();
  return (
    <span role="group" aria-label={t('ideas.modes.label')} className="inline-flex gap-1">
      {MAP_MODES.map((mode: MapMode) => (
        <Button
          key={mode}
          size="small"
          look={board.mode === mode ? 'primary' : 'plain'}
          aria-pressed={board.mode === mode}
          disabled={edit.isPending}
          onClick={() =>
            edit.mutate({ id: board.id, title: board.title, mode, version: board.version })
          }
        >
          {t(`ideas.modes.${mode}`)}
        </Button>
      ))}
    </span>
  );
}

// --------------------------------------------------------------------------------------
// Полотно
// --------------------------------------------------------------------------------------

interface Point {
  x: number;
  y: number;
}

/** Место узла и версия, при которой оно такое на сервере. */
interface Spot extends Point {
  version: number;
}

/** Масштаб и сдвиг полотна. */
interface Frame {
  shiftX: number;
  shiftY: number;
  scale: number;
}

interface Drag {
  id: string;
  startX: number;
  startY: number;
  dx: number;
  dy: number;
  /** Откуда узел взяли: он идёт за указателем от этого места, что бы ни принёс опрос. */
  origin: Point;
  /**
   * Версия, с которой начался перенос; `null` — перенос продолжает свои же, ещё не
   * подтверждённые сервером шаги.
   */
  version: number | null;
  /**
   * Масштаб и сдвиг на время перетаскивания стоят: иначе узел за краем сдвигал бы всю карту, а
   * масштаб менялся бы под пальцем.
   */
  frame: Frame;
}

/** Перенос узла, ещё не дошедший до карты с сервера. */
interface Placed extends Spot {
  /** Запрос в пути: место показывается, что бы ни принёс опрос. */
  busy: boolean;
}

/**
 * Переносы узлов — по очереди на узел.
 *
 * Сервер сверяет версию узла на каждом переносе (инвариант 15), а версия в карте обновится
 * только с перечитыванием. Два быстрых нажатия стрелки с одной версией дали бы второму ложное
 * «запись уже изменили». Поэтому у узла в пути не больше одного запроса; шаги, сделанные за
 * это время, копятся в одну последнюю цель и уходят следом — с версией, которую сервер дал
 * после предыдущего шага. Сервер поднимает версию, только когда место правда изменилось
 * (`services.ideas.move_node`), — так же считается и здесь.
 */
function useMover(mapId: string) {
  const move = useMoveNode();
  const [placed, setPlaced] = useState<Record<string, Placed>>({});
  const [failure, setFailure] = useState<unknown>(null);
  const queued = useRef(new Map<string, Point | null>());

  const send = (id: string, from: Point, to: Point, version: number) => {
    move.mutateAsync({ mapId, id, x: to.x, y: to.y, version }).then(
      () => {
        const after = from.x === to.x && from.y === to.y ? version : version + 1;
        const next = queued.current.get(id);
        if (next) {
          queued.current.set(id, null);
          send(id, to, next, after);
          return;
        }
        queued.current.delete(id);
        setPlaced((current) => {
          const local = current[id];
          return local ? { ...current, [id]: { ...local, version: after, busy: false } } : current;
        });
      },
      (error: unknown) => {
        queued.current.delete(id);
        setFailure(error);
        // Несохранённое место не остаётся на экране: узел встаёт туда, где он на сервере.
        setPlaced((current) => {
          const rest = { ...current };
          delete rest[id];
          return rest;
        });
      },
    );
  };

  /** Где узел сейчас для человека — с его переносами, которых карта с сервера ещё не знает. */
  const spot = (node: MapNode): Spot => {
    const local = placed[node.id];
    return local && (local.busy || node.version < local.version) ? local : node;
  };

  /** Перенос от `from` — места и версии, которые человек видел, начиная перенос. */
  const place = (id: string, from: Spot, to: Point) => {
    setFailure(null);
    setPlaced((current) => ({
      ...current,
      [id]: { x: to.x, y: to.y, version: from.version, busy: true },
    }));
    if (queued.current.has(id)) {
      queued.current.set(id, to);
      return;
    }
    queued.current.set(id, null);
    send(id, { x: from.x, y: from.y }, to, from.version);
  };

  return { spot, place, busy: (id: string) => queued.current.has(id), failure };
}

function Board({ board, editable }: { board: MapCard; editable: boolean }) {
  const { t } = useTranslation();
  const mover = useMover(board.id);
  const describedBy = useId();
  const [selected, setSelected] = useState<string | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const moved = useRef(false);
  const frame = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ width: 0, height: 0 });

  // Карта вписывается в окно: картина целиком видна сразу (ТЗ 1 — понять за полминуты).
  useEffect(() => {
    const element = frame.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const measure = () => setBox({ width: element.clientWidth, height: element.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const position = (node: MapNode): Point => {
    if (drag?.id === node.id) return { x: drag.origin.x + drag.dx, y: drag.origin.y + drag.dy };
    const { x, y } = mover.spot(node);
    return { x, y };
  };

  // Вписывается карта по местам без перетаскиваемого узла, а пока его тянут, масштаб и
  // сдвиг стоят такими, какими были при касании.
  const fitted = ((): Frame => {
    const spots = board.node_list.map(mover.spot);
    const shiftX = MARGIN - Math.min(0, ...spots.map((each) => each.x));
    const shiftY = MARGIN - Math.min(0, ...spots.map((each) => each.y));
    const extentX = Math.max(...spots.map((each) => each.x + shiftX + NODE_WIDTH + MARGIN), 0);
    const extentY = Math.max(...spots.map((each) => each.y + shiftY + NODE_HEIGHT + MARGIN), 0);
    const scale =
      box.width && extentX && extentY
        ? Math.min(1, Math.max(MIN_SCALE, Math.min(box.width / extentX, box.height / extentY)))
        : 1;
    return { shiftX, shiftY, scale };
  })();
  const { shiftX, shiftY, scale } = drag?.frame ?? fitted;
  const points = board.node_list.map(position);
  const width = Math.max(
    box.width / scale,
    ...points.map((each) => each.x + shiftX + NODE_WIDTH + MARGIN),
  );
  const height = Math.max(
    box.height / scale,
    ...points.map((each) => each.y + shiftY + NODE_HEIGHT + MARGIN),
  );
  const byId = new Map(board.node_list.map((node) => [node.id, node]));

  const onPointerDown = (event: ReactPointerEvent<HTMLButtonElement>, node: MapNode) => {
    if (!editable) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    moved.current = false;
    const from = mover.spot(node);
    setDrag({
      id: node.id,
      startX: event.clientX,
      startY: event.clientY,
      dx: 0,
      dy: 0,
      origin: { x: from.x, y: from.y },
      version: mover.busy(node.id) ? null : from.version,
      frame: fitted,
    });
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!drag) return;
    const dx = (event.clientX - drag.startX) / drag.frame.scale;
    const dy = (event.clientY - drag.startY) / drag.frame.scale;
    if (Math.abs(dx) + Math.abs(dy) > DRAG_THRESHOLD) moved.current = true;
    setDrag({ ...drag, dx, dy });
  };
  const onPointerUp = (node: MapNode) => {
    if (drag?.id === node.id && moved.current) {
      const to = {
        x: Math.round(drag.origin.x + drag.dx),
        y: Math.round(drag.origin.y + drag.dy),
      };
      // Версия — та, при которой узел взяли: чужой перенос, пришедший опросом посреди
      // перетаскивания, даёт честный конфликт, а не «чужое место плюс моё смещение».
      const from =
        drag.version === null ? mover.spot(node) : { ...drag.origin, version: drag.version };
      mover.place(node.id, from, to);
    }
    setDrag(null);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, node: MapNode) => {
    if (!editable) return;
    const delta = {
      ArrowLeft: [-KEY_STEP, 0],
      ArrowRight: [KEY_STEP, 0],
      ArrowUp: [0, -KEY_STEP],
      ArrowDown: [0, KEY_STEP],
    }[event.key];
    if (!delta) return;
    event.preventDefault();
    const from = mover.spot(node);
    mover.place(node.id, from, { x: from.x + delta[0]!, y: from.y + delta[1]! });
  };

  const chosen = selected ? byId.get(selected) : undefined;

  return (
    <div className={cn('grid gap-3', editable && 'lg:grid-cols-[1fr_320px]')}>
      <div
        ref={frame}
        className="relative h-[70vh] overflow-auto rounded-[var(--radius-lg)] border border-line bg-sunken"
        aria-label={t('ideas.canvas.label')}
        role="region"
      >
        <div className="relative" style={{ width: width * scale, height: height * scale }}>
          <div
            className="absolute top-0 left-0"
            style={{ width, height, transform: `scale(${scale})`, transformOrigin: '0 0' }}
          >
            <svg
              className="absolute inset-0 text-line-strong"
              width={width}
              height={height}
              aria-hidden="true"
            >
              {board.node_list.map((node) => {
                const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
                if (!parent) return null;
                const from = position(parent);
                const to = position(node);
                return (
                  <line
                    key={node.id}
                    x1={from.x + shiftX + NODE_WIDTH / 2}
                    y1={from.y + shiftY + NODE_HEIGHT / 2}
                    x2={to.x + shiftX + NODE_WIDTH / 2}
                    y2={to.y + shiftY + NODE_HEIGHT / 2}
                    stroke="currentColor"
                    strokeWidth={2}
                  />
                );
              })}
            </svg>
            {board.node_list.map((node) => {
              const at = position(node);
              const unlinked = board.mode === 'structure' && !node.link;
              return (
                <button
                  key={node.id}
                  type="button"
                  aria-pressed={selected === node.id}
                  // Имя — подпись узла, а код записи и ступень Пульта звучат описанием: без
                  // них скринридер не слышал бы главного сигнала режима «Структура».
                  aria-label={node.text}
                  aria-describedby={
                    board.mode === 'structure' ? `${describedBy}-${node.id}` : undefined
                  }
                  onPointerDown={(event) => onPointerDown(event, node)}
                  onPointerMove={onPointerMove}
                  onPointerUp={() => onPointerUp(node)}
                  onPointerCancel={() => setDrag(null)}
                  onClick={(event) => {
                    // Щелчок после перетаскивания — не выбор. Enter, Space и скринридер дают
                    // щелчок без указателя (detail = 0): он выбирает всегда, а признак
                    // перетаскивания гасится на любом щелчке, а не только на следующем касании.
                    const dragged = moved.current && event.detail !== 0;
                    moved.current = false;
                    if (!dragged) setSelected(selected === node.id ? null : node.id);
                  }}
                  onKeyDown={(event) => onKeyDown(event, node)}
                  style={{
                    left: at.x + shiftX,
                    top: at.y + shiftY,
                    width: NODE_WIDTH,
                    minHeight: NODE_HEIGHT,
                  }}
                  className={cn(
                    'absolute flex touch-none flex-col items-start gap-1 rounded-[var(--radius)] border bg-card p-2 text-left text-sm',
                    node.parent_id === null
                      ? 'border-line-accent font-semibold'
                      : 'border-line-strong',
                    unlinked && 'border-dashed',
                    selected === node.id && 'ring-2 ring-accent',
                    editable && 'cursor-grab active:cursor-grabbing',
                  )}
                >
                  <span className="text-ink-strong">{node.text}</span>
                  {board.mode === 'structure' ? (
                    <NodeLink node={node} id={`${describedBy}-${node.id}`} />
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>
      {editable ? (
        <aside className="flex flex-col gap-3">
          <AddNode board={board} parent={chosen ?? null} />
          {chosen ? (
            <NodePanel
              key={chosen.id}
              board={board}
              node={chosen}
              onGone={() => setSelected(null)}
            />
          ) : (
            <p className="text-sm text-ink-muted">{t('ideas.canvas.pick')}</p>
          )}
          {mover.failure ? (
            <p role="alert" className="text-sm text-burn-ink">
              {describeError(mover.failure)}
            </p>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}

function NodeLink({ node, id }: { node: MapNode; id?: string }) {
  const { t } = useTranslation();
  if (!node.link)
    return (
      <span id={id} className="text-xs text-ink-muted">
        {t('ideas.canvas.unlinked')}
      </span>
    );
  return (
    <span id={id} className="inline-flex flex-wrap items-center gap-1 text-xs text-ink-muted">
      <span className="numeric">{node.link.code}</span>
      {node.step ? (
        <Signal state={STEP_SIGNAL[node.step]}>{t(`pult.steps.${node.step}`)}</Signal>
      ) : null}
    </span>
  );
}

function AddNode({ board, parent }: { board: MapCard; parent: MapNode | null }) {
  const { t } = useTranslation();
  const add = useAddNode();
  const [text, setText] = useState('');
  const siblings = board.node_list.filter((each) => each.parent_id === (parent?.id ?? null)).length;
  return (
    <form
      className="flex flex-col gap-2 rounded-[var(--radius-lg)] border border-line bg-card p-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (!text.trim()) return;
        // Новый узел — справа от родителя, ступенькой вниз: не ложится на соседей.
        const x = parent ? parent.x + NODE_WIDTH + 60 : 40;
        const y = parent
          ? parent.y + siblings * (NODE_HEIGHT + 24)
          : 40 + siblings * (NODE_HEIGHT + 24);
        add.mutate(
          { mapId: board.id, text, parent_id: parent?.id ?? null, x, y },
          { onSuccess: () => setText('') },
        );
      }}
    >
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        {parent ? t('ideas.canvas.addChild', { parent: parent.text }) : t('ideas.canvas.addRoot')}
        <input className={FIELD} value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <Button type="submit" size="small" disabled={add.isPending || !text.trim()}>
        <Plus className="size-4" aria-hidden="true" />
        {t('ideas.canvas.add')}
      </Button>
      {add.isError ? (
        <p role="alert" className="text-sm text-burn-ink">
          {describeError(add.error)}
        </p>
      ) : null}
    </form>
  );
}

function NodePanel({ board, node, onGone }: { board: MapCard; node: MapNode; onGone: () => void }) {
  const { t } = useTranslation();
  const edit = useEditNode();
  const parent = useSetParent();
  const convert = useConvertNode();
  const remove = useDeleteNode();
  // Черновик подписи помнит версию, с которой человек начал печатать. Опрос раз в 5 с
  // приносит свежий узел, и его версия в запросе молча затёрла бы чужую правку (инвариант
  // 15). Пока поле не трогали, оно показывает подпись с сервера.
  const [draft, setDraft] = useState<{ text: string; version: number } | null>(null);
  const text = draft?.text ?? node.text;
  const [type, setType] = useState(board.project_types[0]?.code ?? '');
  const [confirming, setConfirming] = useState(false);
  const branch = useMemo(() => descendants(board.node_list, node.id), [board.node_list, node.id]);
  const failure = edit.error ?? parent.error ?? convert.error ?? remove.error;

  return (
    <section
      aria-label={t('ideas.node.label')}
      className="flex flex-col gap-3 rounded-[var(--radius-lg)] border border-line bg-card p-3"
    >
      <form
        className="flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!draft) return;
          edit.mutate(
            { mapId: board.id, id: node.id, text: draft.text, version: draft.version },
            {
              onSuccess: () => setDraft(null),
              // Конфликт: правка не сохранена, поле показывает подпись второго человека, а
              // сообщение говорит, что внести свою надо ещё раз.
              onError: (error) => {
                if (error instanceof ApiError && error.status === 409) setDraft(null);
              },
            },
          );
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          {t('ideas.node.text')}
          <input
            className={FIELD}
            value={text}
            onChange={(event) =>
              setDraft({ text: event.target.value, version: draft?.version ?? node.version })
            }
          />
        </label>
        <Button
          type="submit"
          size="small"
          disabled={edit.isPending || !draft || !text.trim() || text === node.text}
        >
          {t('ideas.node.save')}
        </Button>
      </form>

      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        {t('ideas.node.parent')}
        <select
          className={FIELD}
          value={node.parent_id ?? ''}
          onChange={(event) =>
            parent.mutate({
              mapId: board.id,
              id: node.id,
              parent_id: event.target.value || null,
              version: node.version,
            })
          }
        >
          <option value="">{t('ideas.node.noParent')}</option>
          {board.node_list
            .filter((each) => !branch.has(each.id))
            .map((each) => (
              <option key={each.id} value={each.id}>
                {each.text}
              </option>
            ))}
        </select>
      </label>

      {node.link ? (
        <p className="text-sm text-ink">
          {t(`ideas.link.${node.link.type}`, { code: node.link.code, title: node.link.title })}
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            {t('ideas.decision.type')}
            <select
              className={FIELD}
              value={type}
              onChange={(event) => setType(event.target.value)}
            >
              {board.project_types.map((each) => (
                <option key={each.code} value={each.code}>
                  {each.name}
                </option>
              ))}
            </select>
          </label>
          <span className="flex flex-wrap gap-2">
            <Button
              size="small"
              look="primary"
              disabled={convert.isPending || !type}
              onClick={() =>
                convert.mutate({
                  mapId: board.id,
                  id: node.id,
                  kind: 'project',
                  type_code: type,
                  version: node.version,
                })
              }
            >
              {t('ideas.node.toProject')}
            </Button>
            <Button
              size="small"
              disabled={convert.isPending}
              onClick={() =>
                convert.mutate({
                  mapId: board.id,
                  id: node.id,
                  kind: 'task',
                  type_code: null,
                  version: node.version,
                })
              }
            >
              {t('ideas.node.toTask')}
            </Button>
          </span>
        </div>
      )}

      {confirming ? (
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-burn-ink">
            {t('ideas.node.confirm', { count: branch.size })}
          </span>
          <Button
            size="small"
            look="primary"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(
                // Отпечаток — та ветвь, что стоит в вопросе перед глазами человека.
                {
                  mapId: board.id,
                  id: node.id,
                  version: node.version,
                  branch: branchStamp(board.node_list.filter((each) => branch.has(each.id))),
                },
                { onSuccess: onGone },
              )
            }
          >
            {t('ideas.node.remove')}
          </Button>
          <Button size="small" look="quiet" onClick={() => setConfirming(false)}>
            {t('ideas.node.keep')}
          </Button>
        </span>
      ) : (
        <Button size="small" look="quiet" onClick={() => setConfirming(true)}>
          {t('ideas.node.removeBranch')}
        </Button>
      )}
      {failure ? (
        <p role="alert" className="text-sm text-burn-ink">
          {describeError(failure)}
        </p>
      ) : null}
    </section>
  );
}

// --------------------------------------------------------------------------------------
// Контур — телефон
// --------------------------------------------------------------------------------------

function Outline({ board }: { board: MapCard }) {
  const { t } = useTranslation();
  const children = new Map<string | null, MapNode[]>();
  for (const node of board.node_list) {
    children.set(node.parent_id, [...(children.get(node.parent_id) ?? []), node]);
  }
  const known = new Set(board.node_list.map((node) => node.id));
  // Узел, чей родитель не пришёл (ещё не перечитан), — корнем, а не пропадает.
  const roots = board.node_list.filter((node) => !node.parent_id || !known.has(node.parent_id));

  const branch = (nodes: MapNode[], depth: number) => (
    <ul className={cn('flex flex-col gap-1', depth > 0 && 'border-l border-line pl-3')}>
      {nodes.map((node) => (
        <li key={node.id} className="flex flex-col gap-1">
          <span className="flex min-h-touch flex-col justify-center rounded-[var(--radius)] bg-card px-3 py-2">
            <span className={cn('text-ink-strong', depth === 0 && 'font-semibold')}>
              {node.text}
            </span>
            {board.mode === 'structure' ? <NodeLink node={node} /> : null}
          </span>
          {children.get(node.id)?.length ? branch(children.get(node.id)!, depth + 1) : null}
        </li>
      ))}
    </ul>
  );

  return (
    <section aria-label={t('ideas.outline.label')} className="flex flex-col gap-2">
      <p className="text-xs text-ink-muted">{t('ideas.outline.hint')}</p>
      {board.node_list.length === 0 ? <Empty label={t('ideas.outline.empty')} /> : branch(roots, 0)}
    </section>
  );
}
