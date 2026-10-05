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
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { STEP_SIGNAL } from '@/sections/pult/model';
import { describeError } from '@/shared/api/client';
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
                    {formatDate(each.changed_at.slice(0, 10))}
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
  if (board.isError) {
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

interface Drag {
  id: string;
  startX: number;
  startY: number;
  dx: number;
  dy: number;
}

function Board({ board, editable }: { board: MapCard; editable: boolean }) {
  const { t } = useTranslation();
  const move = useMoveNode();
  const [selected, setSelected] = useState<string | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  // Место, куда узел уже перенесён, пока сервер не ответил: иначе узел прыгнул бы назад до
  // следующего опроса. Запоминается с версией — новая версия с сервера его отменяет.
  const [placed, setPlaced] = useState<Record<string, { x: number; y: number; version: number }>>(
    {},
  );
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

  const position = (node: MapNode) => {
    const local = placed[node.id];
    const base = local && local.version === node.version ? local : node;
    if (drag?.id === node.id) return { x: base.x + drag.dx, y: base.y + drag.dy };
    return { x: base.x, y: base.y };
  };

  const points = board.node_list.map(position);
  const minX = Math.min(0, ...points.map((each) => each.x));
  const minY = Math.min(0, ...points.map((each) => each.y));
  const shiftX = MARGIN - minX;
  const shiftY = MARGIN - minY;
  // Масштаб — по местам с сервера, не по перетаскиваемому узлу: иначе полотно дышало бы
  // под пальцем.
  const extentX = Math.max(
    ...board.node_list.map((node) => node.x + shiftX + NODE_WIDTH + MARGIN),
    0,
  );
  const extentY = Math.max(
    ...board.node_list.map((node) => node.y + shiftY + NODE_HEIGHT + MARGIN),
    0,
  );
  const scale =
    box.width && extentX && extentY
      ? Math.min(1, Math.max(MIN_SCALE, Math.min(box.width / extentX, box.height / extentY)))
      : 1;
  const width = Math.max(
    box.width / scale,
    ...points.map((each) => each.x + shiftX + NODE_WIDTH + MARGIN),
  );
  const height = Math.max(
    box.height / scale,
    ...points.map((each) => each.y + shiftY + NODE_HEIGHT + MARGIN),
  );
  const byId = new Map(board.node_list.map((node) => [node.id, node]));

  const place = (node: MapNode, x: number, y: number) => {
    setPlaced((current) => ({ ...current, [node.id]: { x, y, version: node.version } }));
    move.mutate({ mapId: board.id, id: node.id, x, y, version: node.version });
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLButtonElement>, node: MapNode) => {
    if (!editable) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    moved.current = false;
    setDrag({ id: node.id, startX: event.clientX, startY: event.clientY, dx: 0, dy: 0 });
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!drag) return;
    const dx = (event.clientX - drag.startX) / scale;
    const dy = (event.clientY - drag.startY) / scale;
    if (Math.abs(dx) + Math.abs(dy) > DRAG_THRESHOLD) moved.current = true;
    setDrag({ ...drag, dx, dy });
  };
  const onPointerUp = (node: MapNode) => {
    if (drag && moved.current) {
      const from = position({ ...node, x: node.x, y: node.y });
      place(node, Math.round(from.x), Math.round(from.y));
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
    const from = position(node);
    place(node, from.x + delta[0]!, from.y + delta[1]!);
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
                  aria-label={node.text}
                  onPointerDown={(event) => onPointerDown(event, node)}
                  onPointerMove={onPointerMove}
                  onPointerUp={() => onPointerUp(node)}
                  onClick={() => {
                    if (!moved.current) setSelected(selected === node.id ? null : node.id);
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
                  {board.mode === 'structure' ? <NodeLink node={node} /> : null}
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
          {move.isError ? (
            <p role="alert" className="text-sm text-burn-ink">
              {describeError(move.error)}
            </p>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}

function NodeLink({ node }: { node: MapNode }) {
  const { t } = useTranslation();
  if (!node.link)
    return <span className="text-xs text-ink-muted">{t('ideas.canvas.unlinked')}</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-xs text-ink-muted">
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
  const [text, setText] = useState(node.text);
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
          edit.mutate({ mapId: board.id, id: node.id, text, version: node.version });
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          {t('ideas.node.text')}
          <input className={FIELD} value={text} onChange={(event) => setText(event.target.value)} />
        </label>
        <Button
          type="submit"
          size="small"
          disabled={edit.isPending || !text.trim() || text === node.text}
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
                { mapId: board.id, id: node.id, version: node.version },
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
