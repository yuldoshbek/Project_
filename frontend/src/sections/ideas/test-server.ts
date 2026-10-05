/**
 * Сервер «Идей и карт» в памяти — для тестов экрана.
 *
 * Отвечает на те же пути, что `/api/v1/ideas…` и `/api/v1/maps…`, той же формой. Правила —
 * как у сервера (`backend/app/domain/ideas.py`): ждущие решения — дольше всех первой,
 * решение заводит запись и ссылку, решает только руководитель. Сам сервер проверяет
 * `backend/tests/test_ideas.py`; здесь — что экран делает с его ответами.
 */

import type { Idea, IdeasView, MapCard, MapNode, MapSummary, Outcome } from './model';

type Role = 'assistant' | 'leader';

const TODAY = '2026-10-05';

export class FakeIdeas {
  items: Idea[];
  maps: MapSummary[];
  nodes: Record<string, MapNode[]>;
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
      idea('i-pasture', 'Спутниковый мониторинг пастбищ', { author: 'leader' }),
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
        changed_at: `${TODAY}T04:00:00Z`,
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
    const waiting = this.items
      .filter((each) => each.step === 'review')
      .sort((a, b) => (a.review_at ?? '').localeCompare(b.review_at ?? ''));
    return {
      as_of: `${TODAY}T07:00:00Z`,
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
    if (!summary) throw new Error(`нет карты ${id}`);
    return {
      ...summary,
      node_list: this.nodes[id] ?? [],
      project_types: this.view().project_types,
    };
  }

  private idea(id: string): Idea {
    const found = this.items.find((each) => each.id === id);
    if (!found) throw new Error(`нет идеи ${id}`);
    return found;
  }

  create(text: string, role: Role): string {
    this.counter += 1;
    const id = `i-new-${this.counter}`;
    this.items.unshift({
      id,
      text: text.trim(),
      author: role,
      step: 'draft',
      outcome: null,
      created_at: `${TODAY}T07:00:00Z`,
      review_at: null,
      decided_at: null,
      waiting_days: 0,
      link: null,
      version: 1,
    });
    return id;
  }

  review(id: string): void {
    const idea = this.idea(id);
    Object.assign(idea, {
      step: 'review',
      outcome: null,
      review_at: `${TODAY}T07:00:00Z`,
      waiting_days: 0,
      version: idea.version + 1,
    });
  }

  decide(id: string, outcome: Outcome): string | null {
    const idea = this.idea(id);
    this.counter += 1;
    const created = outcome === 'postponed' ? null : `${outcome}-${this.counter}`;
    Object.assign(idea, {
      step: 'decided',
      outcome,
      waiting_days: 0,
      link: created
        ? {
            type: outcome,
            id: created,
            code: outcome === 'project' ? `PR-0${this.counter}` : `Т-0${this.counter}`,
            title: idea.text,
          }
        : null,
      version: idea.version + 1,
    });
    return created;
  }

  addNode(mapId: string, body: Record<string, unknown>): string {
    this.counter += 1;
    const id = `n-new-${this.counter}`;
    (this.nodes[mapId] ??= []).push({
      id,
      parent_id: (body.parent_id as string | null) ?? null,
      text: String(body.text),
      x: Number(body.x),
      y: Number(body.y),
      link: null,
      step: null,
      deviation: 0,
      version: 1,
    });
    return id;
  }

  node(mapId: string, id: string): MapNode {
    const found = this.nodes[mapId]?.find((each) => each.id === id);
    if (!found) throw new Error(`нет узла ${id}`);
    return found;
  }
}

type Reply = [number, unknown];

export function handle(
  server: FakeIdeas,
  method: string,
  url: string,
  body: Record<string, unknown> | undefined,
  role: Role,
): Reply | null {
  const [path = url] = url.split('?');
  const input = body ?? {};
  try {
    if (path === '/api/v1/ideas') {
      if (method === 'GET') return [200, server.view()];
      return [201, { id: server.create(String(input.text), role) }];
    }
    const idea = /^\/api\/v1\/ideas\/([^/]+)\/(review|decision)$/.exec(path);
    if (idea) {
      const [, id = '', action] = idea;
      if (action === 'review') {
        server.review(id);
        return [204, undefined];
      }
      if (role !== 'leader') return [403, { detail: 'Решает руководитель' }];
      return [200, { created_id: server.decide(id, input.outcome as Outcome) }];
    }
    const board =
      /^\/api\/v1\/maps\/([^/]+)(?:\/nodes(?:\/([^/]+)(?:\/(position|convert))?)?)?$/.exec(path);
    if (board) {
      const [, mapId = '', nodeId, action] = board;
      if (!nodeId && method === 'GET' && !path.endsWith('/nodes')) return [200, server.card(mapId)];
      if (!nodeId && method === 'POST') return [201, { id: server.addNode(mapId, input) }];
      if (nodeId && action === 'position') {
        const node = server.node(mapId, nodeId);
        Object.assign(node, { x: Number(input.x), y: Number(input.y), version: node.version + 1 });
        return [204, undefined];
      }
      if (nodeId && action === 'convert') {
        const node = server.node(mapId, nodeId);
        node.link = {
          type: input.kind as 'project' | 'task',
          id: 'made',
          code: 'Т-099',
          title: node.text,
        };
        node.version += 1;
        return [201, { id: 'made' }];
      }
    }
    if (url.startsWith('/api/v1/ideas') || url.startsWith('/api/v1/maps')) {
      return [404, { detail: `нет пути ${method} ${url}` }];
    }
    return null;
  } catch (error) {
    return [422, { detail: error instanceof Error ? error.message : String(error) }];
  }
}
