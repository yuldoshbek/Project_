/**
 * Сервер «Идей и карт» в памяти — для тестов экрана.
 *
 * Отвечает на те же пути, что `/api/v1/ideas…` и `/api/v1/maps…` (`backend/app/api/routes/
 * ideas.py`), той же формой и с теми же отказами: устаревшая версия — 409 `stale-data`,
 * нарушенное правило — 422 `rule-violation`, неполный запрос — 422 `validation-error`, решение
 * помощника — 403. Правила — как у сервера (`backend/app/domain/ideas.py`,
 * `backend/app/services/ideas.py`): ждущие решения — по моменту отправки, решённую в проект не
 * отправить и не решить снова, проекту нужен тип, родитель не может быть потомком, ветвь
 * удаляется по версии корня и по числу узлов, которое видел человек. Версия поднимается, только
 * когда запись правда изменилась, — как у SQLAlchemy, которая не пишет строку без изменений.
 *
 * Сам сервер проверяет `backend/tests/test_ideas.py`; здесь — что экран делает с его ответами.
 */

import type { Idea, IdeasView, MapCard, MapMode, MapNode, MapSummary, Outcome } from './model';
import { branchStamp } from './stamp';

type Role = 'assistant' | 'leader';

const TODAY = '2026-10-05';
const NOW = `${TODAY}T07:00:00Z`;

/** Пределы — те же, что в `backend/app/domain/ideas.py`. */
const TEXT_MAX_LENGTH = 1000;
const NODE_TEXT_MAX_LENGTH = 300;
const MAP_TITLE_MAX_LENGTH = 200;
const CANVAS_LIMIT = 20_000;

/** `STALE_VERSION_MESSAGE` из `backend/app/domain/errors.py`. */
export const STALE_MESSAGE =
  'Запись уже изменили, пока вы её редактировали. Ваша правка не сохранена: обновите ' +
  'данные и внесите её ещё раз';

/** Отказ сервера — то, что `app/api/errors.py` отдаёт телом problem+json. */
class Refusal extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    detail: string,
  ) {
    super(detail);
  }
}

const stale = () => new Refusal(409, 'stale-data', STALE_MESSAGE);
const rule = (detail: string) => new Refusal(422, 'rule-violation', detail);
const invalid = () => new Refusal(422, 'validation-error', 'Проверьте заполнение полей');
const missing = (detail: string) => new Refusal(404, 'not-found', detail);

function checkVersion(expected: unknown, actual: number): void {
  if (typeof expected !== 'number' || !Number.isInteger(expected)) throw invalid();
  if (expected !== actual) throw stale();
}

/** Длина проверяется схемой запроса (422), пустота после сжатия пробелов — правилом. */
function cleanText(text: unknown, limit: number): string {
  if (typeof text !== 'string' || text.length === 0 || text.length > limit) throw invalid();
  const cleaned = text.split(/\s+/).filter(Boolean).join(' ');
  if (!cleaned) throw rule('Текст не может быть пустым');
  return cleaned;
}

function coordinate(value: unknown): number {
  if (typeof value !== 'number' || !Number.isInteger(value)) throw invalid();
  if (Math.abs(value) > CANVAS_LIMIT) throw invalid();
  return value;
}

function queryInt(value: string | null, min: number): number {
  if (value === null || !/^-?\d+$/.test(value) || Number(value) < min) throw invalid();
  return Number(value);
}

function mode(value: unknown): MapMode {
  if (value === undefined) return 'sketch';
  if (value !== 'sketch' && value !== 'structure') throw invalid();
  return value;
}

/** Решённую в проект или задачу — нельзя; отложенную — можно (V47). */
function checkOpen(idea: Idea): void {
  if (idea.step === 'decided' && idea.outcome !== 'postponed') throw rule('По идее уже решено');
}

export class FakeIdeas {
  items: Idea[];
  maps: MapSummary[];
  nodes: Record<string, MapNode[]>;
  /** Сбой сети или прокси: запросы `МЕТОД путь`, совпавшие с ним, получают 503. */
  outage: RegExp | null = null;
  private counter = 0;

  constructor() {
    const idea = (id: string, text: string, extra: Partial<Idea>): Idea => ({
      id,
      text,
      author: 'assistant',
      step: 'draft',
      outcome: null,
      created_at: `${TODAY}T05:00:00Z`,
      review_at: null,
      decided_at: null,
      waiting_days: 0,
      link: null,
      version: 1,
      ...extra,
    });
    this.items = [
      // Записана 05.10 в 01:30 по Ташкенту — в UTC это ещё 04.10.
      idea('i-pasture', 'Спутниковый мониторинг пастбищ', {
        author: 'leader',
        created_at: '2026-10-04T20:30:00Z',
      }),
      idea('i-water', 'Ежемесячная сводка по водным ресурсам', {
        step: 'review',
        review_at: '2026-10-02T05:00:00Z',
        waiting_days: 3,
      }),
      idea('i-catalogue', 'Открытый каталог снимков для вузов', {
        step: 'review',
        review_at: '2026-09-26T05:00:00Z',
        waiting_days: 9,
      }),
      idea('i-crops', 'Пилот мониторинга посевов', {
        step: 'decided',
        outcome: 'project',
        created_at: '2026-09-20T05:00:00Z',
        // Решено 04.10 в 02:00 по Ташкенту — в UTC это ещё 03.10.
        decided_at: '2026-10-03T21:00:00Z',
        link: {
          type: 'project',
          id: 'pr-crops',
          code: 'PR-005',
          title: 'Пилот: мониторинг посевов',
        },
      }),
    ];
    this.maps = [
      {
        id: 'm-agro',
        title: 'Мониторинг сельского хозяйства',
        mode: 'structure',
        nodes: 3,
        linked: 1,
        // Изменена 05.10 в 03:00 по Ташкенту.
        changed_at: '2026-10-04T22:00:00Z',
        version: 1,
      },
    ];
    const node = (
      id: string,
      text: string,
      parent: string | null,
      extra: Partial<MapNode> = {},
    ): MapNode => ({
      id,
      parent_id: parent,
      text,
      x: parent ? 300 : 40,
      y: parent ? 160 : 40,
      link: null,
      step: null,
      deviation: 0,
      version: 1,
      ...extra,
    });
    this.nodes = {
      'm-agro': [
        node('n-root', 'Мониторинг сельского хозяйства', null),
        node('n-drought', 'Засуха', 'n-root', {
          link: { type: 'project', id: 'pr-drought', code: 'PR-003', title: 'Засуха' },
          step: 'overdue',
          deviation: 3,
        }),
        node('n-pasture', 'Пастбища', 'n-root', { y: 300 }),
      ],
    };
  }

  view(): IdeasView {
    // Как `domain.ideas.awaiting`: по моменту отправки, при равенстве — по идентификатору.
    const waiting = this.items
      .filter((each) => each.step === 'review')
      .sort(
        (a, b) => (a.review_at ?? '').localeCompare(b.review_at ?? '') || a.id.localeCompare(b.id),
      );
    return {
      as_of: NOW,
      questions: [
        {
          key: 'awaiting',
          count: waiting.length,
          oldest_days: waiting[0]?.waiting_days ?? 0,
          oldest_id: waiting[0]?.id ?? null,
          rows: waiting.map((each) => each.id),
        },
      ],
      items: this.items,
      maps: this.maps.map((each) => ({
        ...each,
        nodes: this.nodes[each.id]?.length ?? 0,
        linked: (this.nodes[each.id] ?? []).filter((node) => node.link).length,
      })),
      project_types: [
        { code: 'industry_pilot', name: 'Отраслевой пилот' },
        { code: 'regulation', name: 'Нормативный акт' },
      ],
      is_demo: true,
    };
  }

  card(id: string): MapCard {
    const summary = this.view().maps.find((each) => each.id === id);
    if (!summary) throw missing('Карта не найдена');
    return {
      ...summary,
      node_list: this.nodes[id] ?? [],
      project_types: this.view().project_types,
    };
  }

  idea(id: string): Idea {
    const found = this.items.find((each) => each.id === id);
    if (!found) throw missing('Идея не найдена');
    return found;
  }

  node(mapId: string, id: string): MapNode {
    const found = this.nodes[mapId]?.find((each) => each.id === id);
    if (!found) throw missing('Узел не найден');
    return found;
  }

  private map(id: string): MapSummary {
    const found = this.maps.find((each) => each.id === id);
    if (!found) throw missing('Карта не найдена');
    return found;
  }

  /** Запись, которую заводит решение или превращение узла, — как `services.ideas._create_work`. */
  private work(kind: unknown, typeCode: unknown, title: string) {
    if (kind !== 'project' && kind !== 'task') throw invalid();
    if (kind === 'project' && !typeCode) throw rule('Для проекта нужен тип');
    this.counter += 1;
    return {
      type: kind,
      id: `${kind}-${this.counter}`,
      code: kind === 'project' ? `PR-0${this.counter}` : `Т-0${this.counter}`,
      title,
    } as const;
  }

  create(text: unknown, role: Role): string {
    const cleaned = cleanText(text, TEXT_MAX_LENGTH);
    this.counter += 1;
    const id = `i-new-${this.counter}`;
    this.items.unshift({
      id,
      text: cleaned,
      author: role,
      step: 'draft',
      outcome: null,
      created_at: NOW,
      review_at: null,
      decided_at: null,
      waiting_days: 0,
      link: null,
      version: 1,
    });
    return id;
  }

  editIdea(id: string, text: unknown, version: unknown): void {
    const idea = this.idea(id);
    const cleaned = cleanText(text, TEXT_MAX_LENGTH);
    checkVersion(version, idea.version);
    if (idea.text !== cleaned) Object.assign(idea, { text: cleaned, version: idea.version + 1 });
  }

  review(id: string, version: unknown): void {
    const idea = this.idea(id);
    checkVersion(version, idea.version);
    if (idea.step === 'review') throw rule('Идея уже на рассмотрении');
    checkOpen(idea);
    Object.assign(idea, {
      step: 'review',
      outcome: null,
      decided_at: null,
      review_at: NOW,
      waiting_days: 0,
      version: idea.version + 1,
    });
  }

  decide(id: string, outcome: unknown, typeCode: unknown, version: unknown): string | null {
    if (outcome !== 'project' && outcome !== 'task' && outcome !== 'postponed') throw invalid();
    const idea = this.idea(id);
    checkVersion(version, idea.version);
    checkOpen(idea);
    const link = outcome === 'postponed' ? null : this.work(outcome, typeCode, idea.text);
    Object.assign(idea, {
      step: 'decided',
      outcome: outcome satisfies Outcome,
      decided_at: NOW,
      waiting_days: 0,
      link,
      version: idea.version + 1,
    });
    return link?.id ?? null;
  }

  createMap(title: unknown, value: unknown): string {
    const cleaned = cleanText(title, MAP_TITLE_MAX_LENGTH);
    this.counter += 1;
    const id = `m-new-${this.counter}`;
    this.maps.push({
      id,
      title: cleaned,
      mode: mode(value),
      nodes: 0,
      linked: 0,
      changed_at: NOW,
      version: 1,
    });
    this.nodes[id] = [];
    return id;
  }

  editMap(id: string, title: unknown, value: unknown, version: unknown): void {
    const found = this.map(id);
    const cleaned = cleanText(title, MAP_TITLE_MAX_LENGTH);
    const next = mode(value);
    checkVersion(version, found.version);
    if (found.title !== cleaned || found.mode !== next) {
      Object.assign(found, { title: cleaned, mode: next, version: found.version + 1 });
    }
  }

  /** Родитель — узел той же карты и не потомок узла: иначе связи замкнутся в кольцо. */
  private checkParent(mapId: string, nodeId: string | null, parentId: string | null): void {
    if (parentId === null) return;
    const parents = new Map((this.nodes[mapId] ?? []).map((each) => [each.id, each.parent_id]));
    if (!parents.has(parentId)) throw rule('Родитель — узел другой карты или его нет');
    const seen = new Set<string>();
    let current: string | null = parentId;
    while (current !== null && !seen.has(current)) {
      if (current === nodeId) throw rule('Узел не может стать потомком самого себя');
      seen.add(current);
      current = parents.get(current) ?? null;
    }
  }

  addNode(mapId: string, body: Record<string, unknown>): string {
    this.map(mapId);
    const text = cleanText(body.text, NODE_TEXT_MAX_LENGTH);
    const x = coordinate(body.x);
    const y = coordinate(body.y);
    const parent = (body.parent_id as string | null | undefined) ?? null;
    this.checkParent(mapId, null, parent);
    this.counter += 1;
    const id = `n-new-${this.counter}`;
    (this.nodes[mapId] ??= []).push({
      id,
      parent_id: parent,
      text,
      x,
      y,
      link: null,
      step: null,
      deviation: 0,
      version: 1,
    });
    return id;
  }

  editNode(mapId: string, id: string, text: unknown, version: unknown): void {
    const node = this.node(mapId, id);
    const cleaned = cleanText(text, NODE_TEXT_MAX_LENGTH);
    checkVersion(version, node.version);
    if (node.text !== cleaned) Object.assign(node, { text: cleaned, version: node.version + 1 });
  }

  moveNode(mapId: string, id: string, x: unknown, y: unknown, version: unknown): void {
    const node = this.node(mapId, id);
    const nextX = coordinate(x);
    const nextY = coordinate(y);
    checkVersion(version, node.version);
    if (node.x !== nextX || node.y !== nextY) {
      Object.assign(node, { x: nextX, y: nextY, version: node.version + 1 });
    }
  }

  setParent(mapId: string, id: string, parentId: unknown, version: unknown): void {
    const node = this.node(mapId, id);
    checkVersion(version, node.version);
    const parent = (parentId as string | null | undefined) ?? null;
    this.checkParent(mapId, id, parent);
    if (node.parent_id !== parent)
      Object.assign(node, { parent_id: parent, version: node.version + 1 });
  }

  /** Узел и все его потомки — как `domain.ideas.subtree`. */
  branch(mapId: string, root: string): Set<string> {
    const found = new Set([root]);
    let grew = true;
    while (grew) {
      grew = false;
      for (const each of this.nodes[mapId] ?? []) {
        if (each.parent_id && found.has(each.parent_id) && !found.has(each.id)) {
          found.add(each.id);
          grew = true;
        }
      }
    }
    return found;
  }

  deleteNode(mapId: string, id: string, version: string | null, branch: string | null): number {
    const expected = queryInt(version, Number.MIN_SAFE_INTEGER);
    if (!branch || !/^[0-9a-f]{8}$/.test(branch)) throw invalid();
    const node = this.node(mapId, id);
    checkVersion(expected, node.version);
    const gone = this.branch(mapId, id);
    const seen = (this.nodes[mapId] ?? []).filter((each) => gone.has(each.id));
    if (branchStamp(seen) !== branch) throw stale();
    this.nodes[mapId] = (this.nodes[mapId] ?? []).filter((each) => !gone.has(each.id));
    return gone.size;
  }

  convert(mapId: string, id: string, body: Record<string, unknown>): string {
    if (body.kind !== 'project' && body.kind !== 'task') {
      throw body.kind === 'postponed' ? rule('Узел превращается в проект или задачу') : invalid();
    }
    const node = this.node(mapId, id);
    checkVersion(body.version, node.version);
    if (node.link) throw rule('Узел уже связан с записью');
    const link = this.work(body.kind, body.type_code, node.text);
    Object.assign(node, { link, version: node.version + 1 });
    return link.id;
  }
}

type Reply = [number, unknown];

const NO_CONTENT: Reply = [204, undefined];

function route(
  server: FakeIdeas,
  method: string,
  path: string,
  input: Record<string, unknown>,
  query: URLSearchParams,
  role: Role,
): Reply | null {
  if (path === '/api/v1/ideas') {
    if (method === 'GET') return [200, server.view()];
    if (method === 'POST') return [201, { id: server.create(input.text, role) }];
    return null;
  }
  const idea = /^\/api\/v1\/ideas\/([^/]+)(?:\/(review|decision))?$/.exec(path);
  if (idea) {
    const [, id = '', action] = idea;
    if (!action && method === 'PUT') {
      server.editIdea(id, input.text, input.version);
      return NO_CONTENT;
    }
    if (action === 'review' && method === 'PUT') {
      server.review(id, input.version);
      return NO_CONTENT;
    }
    if (action === 'decision' && method === 'POST') {
      if (role !== 'leader') {
        return [403, { type: '/problems/permission-denied', detail: 'Решает руководитель' }];
      }
      return [
        200,
        { created_id: server.decide(id, input.outcome, input.type_code, input.version) },
      ];
    }
    return null;
  }
  if (path === '/api/v1/maps') {
    return method === 'POST' ? [201, { id: server.createMap(input.title, input.mode) }] : null;
  }
  const board =
    /^\/api\/v1\/maps\/([^/]+)(\/nodes(?:\/([^/]+)(?:\/(position|parent|convert))?)?)?$/.exec(path);
  if (!board) return null;
  const [, mapId = '', nodes, nodeId, action] = board;
  if (!nodes) {
    if (method === 'GET') return [200, server.card(mapId)];
    if (method === 'PUT') {
      server.editMap(mapId, input.title, input.mode, input.version);
      return NO_CONTENT;
    }
    return null;
  }
  if (!nodeId) return method === 'POST' ? [201, { id: server.addNode(mapId, input) }] : null;
  if (!action && method === 'PUT') {
    server.editNode(mapId, nodeId, input.text, input.version);
    return NO_CONTENT;
  }
  if (!action && method === 'DELETE') {
    return [
      200,
      { deleted: server.deleteNode(mapId, nodeId, query.get('version'), query.get('branch')) },
    ];
  }
  if (action === 'position' && method === 'PUT') {
    server.moveNode(mapId, nodeId, input.x, input.y, input.version);
    return NO_CONTENT;
  }
  if (action === 'parent' && method === 'PUT') {
    server.setParent(mapId, nodeId, input.parent_id, input.version);
    return NO_CONTENT;
  }
  if (action === 'convert' && method === 'POST') {
    return [201, { id: server.convert(mapId, nodeId, input) }];
  }
  return null;
}

export function handle(
  server: FakeIdeas,
  method: string,
  url: string,
  body: Record<string, unknown> | undefined,
  role: Role,
): Reply | null {
  const [path = url, search = ''] = url.split('?');
  if (!path.startsWith('/api/v1/ideas') && !path.startsWith('/api/v1/maps')) return null;
  if (server.outage?.test(`${method} ${path}`)) {
    return [503, { type: '/problems/http-503', detail: 'Сервис временно недоступен' }];
  }
  try {
    const [status, answer] = route(
      server,
      method,
      path,
      body ?? {},
      new URLSearchParams(search),
      role,
    ) ?? [404, { detail: `нет пути ${method} ${url}` }];
    // Ответ — копия, как после сети: экран не должен держать живые записи сервера, иначе
    // правка «второго человека» в тесте незаметно меняла бы и то, что экран уже показал.
    return [status, answer === undefined ? undefined : structuredClone(answer)];
  } catch (error) {
    if (error instanceof Refusal) {
      return [error.status, { type: `/problems/${error.code}`, detail: error.message }];
    }
    throw error;
  }
}
