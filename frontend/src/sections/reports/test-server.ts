/**
 * Сервер «Докладов и мероприятий» в памяти — для тестов экрана.
 *
 * Отвечает на те же пути, что `/api/v1/preparations…`, той же формой. Правила — как у
 * сервера (`backend/app/domain/preparations.py`): запрос просрочен, если срок прошёл, а
 * сведений нет; «кто задерживает» — по источникам, дольше всех первым. Сам сервер проверяет
 * `backend/tests/test_preparations.py`; здесь — что экран делает с его ответами.
 */

import type { Step } from '@/sections/pult/model';

import type {
  Delay,
  InfoRequest,
  PreparationCard,
  PreparationRow,
  PrepStage,
  ReportsView,
} from './model';

const DAY_MS = 86_400_000;

interface Stored extends Omit<
  PreparationCard,
  'checklist' | 'requests' | 'delays' | 'step' | 'deviation' | 'days_left'
> {
  step: Step | null;
}

export class FakeReports {
  private readonly today: string;
  private items: Stored[];
  private counter = 0;

  constructor(now: Date = new Date('2026-10-05T07:00:00Z')) {
    this.today = now.toISOString().slice(0, 10);
    const on = (days: number) => new Date(now.getTime() + days * DAY_MS).toISOString().slice(0, 10);
    const request = (
      id: string,
      what: string,
      source: InfoRequest['source'],
      due: number | null,
      received: number | null,
    ): InfoRequest => ({
      id,
      what,
      source,
      due_on: due === null ? null : on(due),
      received_on: received === null ? null : on(received),
      state: 'requested',
      late_days: 0,
      version: 1,
    });
    this.items = [
      {
        id: 'p-drought',
        kind: 'report',
        title: 'Об итогах космического мониторинга засухи',
        addressee: 'cabinet',
        show_on: on(9),
        start_on: on(-10),
        responsible: { id: 'p-rakhimov', name: 'Рахимов Ш.' },
        stage: 'data',
        link: null,
        step: null,
        items: [
          { id: 'i1', text: 'Тезисы', is_done: true, version: 1 },
          { id: 'i2', text: 'Карты по областям', is_done: false, version: 1 },
        ],
        info_requests: [
          request(
            'r1',
            'Данные о засухе',
            { kind: 'organization', id: 'o-eco', name: 'Министерство экологии' },
            -4,
            null,
          ),
          request(
            'r2',
            'Карты районов',
            { kind: 'organization', id: 'o-center', name: 'Центр' },
            -1,
            null,
          ),
          request(
            'r3',
            'Справка о воде',
            { kind: 'person', id: 'p-yusupova', name: 'Юсупова Д.' },
            -5,
            -2,
          ),
        ],
        version: 1,
      },
      {
        id: 'p-quarter',
        kind: 'report',
        title: 'Ежеквартальная справка для Администрации Президента',
        addressee: 'administration',
        show_on: on(3),
        start_on: on(-20),
        responsible: { id: 'p-karimov', name: 'Каримов А.' },
        stage: 'approval',
        link: null,
        step: 'burning',
        items: [],
        info_requests: [],
        version: 1,
      },
      {
        id: 'p-satellite',
        kind: 'report',
        title: 'О ходе программы спутниковой группировки',
        addressee: 'prime_minister',
        show_on: on(20),
        start_on: on(-2),
        responsible: null,
        stage: 'theses',
        link: null,
        step: null,
        items: [],
        info_requests: [],
        version: 1,
      },
    ];
  }

  private days(from: string, to: string): number {
    return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
  }

  private requestView(request: InfoRequest): InfoRequest {
    if (request.received_on) return { ...request, state: 'received', late_days: 0 };
    if (request.due_on && request.due_on < this.today) {
      return { ...request, state: 'overdue', late_days: this.days(request.due_on, this.today) };
    }
    return { ...request, state: 'requested', late_days: 0 };
  }

  card(id: string): PreparationCard {
    const stored = this.items.find((each) => each.id === id);
    if (!stored) throw new Error(`нет подготовки ${id}`);
    const requests = stored.info_requests.map((each) => this.requestView(each));
    const groups = new Map<string, Delay>();
    for (const each of requests) {
      if (each.state !== 'overdue') continue;
      const key = `${each.source.kind}:${each.source.id}`;
      const entry = groups.get(key) ?? { source: each.source, count: 0, days: 0, requests: [] };
      entry.count += 1;
      entry.days = Math.max(entry.days, each.late_days);
      entry.requests.push(each.id);
      groups.set(key, entry);
    }
    return {
      ...stored,
      info_requests: requests,
      checklist: {
        done: stored.items.filter((each) => each.is_done).length,
        total: stored.items.length,
      },
      requests: {
        total: requests.length,
        received: requests.filter((each) => each.state === 'received').length,
        overdue: requests.filter((each) => each.state === 'overdue').length,
      },
      delays: [...groups.values()].sort((a, b) => b.days - a.days),
      days_left: this.days(this.today, stored.show_on),
      deviation: stored.step === 'burning' ? this.days(this.today, stored.show_on) : 0,
    };
  }

  view(): ReportsView {
    // Строка списка — карточка без длинных частей: пунктов и запросов.
    const rows: PreparationRow[] = this.items.map((each) => {
      const row: Partial<PreparationCard> = { ...this.card(each.id) };
      delete row.items;
      delete row.info_requests;
      return row as PreparationRow;
    });
    const missing = rows.filter((each) => each.requests.total - each.requests.received > 0);
    const nearest = [...missing].sort((a, b) => a.show_on.localeCompare(b.show_on))[0];
    return {
      as_of: `${this.today}T07:00:00Z`,
      questions: [
        {
          key: 'readiness',
          count: missing.length,
          rows: missing.map((each) => each.id),
          nearest: nearest
            ? {
                id: nearest.id,
                title: nearest.title,
                days_left: nearest.days_left,
                missing: nearest.requests.total - nearest.requests.received,
                delay: nearest.delays[0] ?? null,
              }
            : null,
        },
        {
          key: 'start_now',
          count: rows.filter((each) => each.stage === 'theses').length,
          rows: rows.filter((each) => each.stage === 'theses').map((each) => each.id),
        },
      ],
      items: rows,
      people: [
        { id: 'p-karimov', name: 'Каримов А.' },
        { id: 'p-yusupova', name: 'Юсупова Д.' },
      ],
      organizations: [{ id: 'o-eco', name: 'Министерство экологии', short_name: null }],
      projects: [],
      is_demo: true,
    };
  }

  private find(id: string): Stored {
    const found = this.items.find((each) => each.id === id);
    if (!found) throw new Error(`нет подготовки ${id}`);
    return found;
  }

  create(body: Record<string, unknown>): string {
    this.counter += 1;
    const id = `p-new-${this.counter}`;
    this.items.push({
      id,
      kind: body.kind as Stored['kind'],
      title: String(body.title).trim(),
      addressee: (body.addressee as Stored['addressee']) ?? null,
      show_on: String(body.show_on),
      start_on: (body.start_on as string | null) ?? null,
      responsible: null,
      stage: 'theses',
      link: null,
      step: null,
      items: [],
      info_requests: [],
      version: 1,
    });
    return id;
  }

  setStage(id: string, stage: PrepStage): void {
    const stored = this.find(id);
    stored.stage = stage;
    stored.version += 1;
  }

  receive(id: string, requestId: string, received: string | null): void {
    const request = this.find(id).info_requests.find((each) => each.id === requestId);
    if (!request) throw new Error(`нет запроса ${requestId}`);
    request.received_on = received;
    request.version += 1;
  }

  addItem(id: string, text: string): string {
    this.counter += 1;
    const item = { id: `i-new-${this.counter}`, text, is_done: false, version: 1 };
    this.find(id).items.push(item);
    return item.id;
  }

  toggle(id: string, itemId: string, done: boolean): void {
    const item = this.find(id).items.find((each) => each.id === itemId);
    if (!item) throw new Error(`нет пункта ${itemId}`);
    item.is_done = done;
    item.version += 1;
  }
}

type Reply = [number, unknown];

export function handle(
  server: FakeReports,
  method: string,
  path: string,
  body: Record<string, unknown> | undefined,
  role: 'assistant' | 'leader',
): Reply | null {
  const BASE = '/api/v1/preparations';
  if (!path.startsWith(BASE)) return null;
  const rest = path.slice(BASE.length).split('/').filter(Boolean);
  const input = body ?? {};
  try {
    if (method === 'GET' && rest.length === 0) return [200, server.view()];
    if (method === 'GET' && rest.length === 1) return [200, server.card(String(rest[0]))];
    if (role !== 'assistant') return [403, { detail: 'Это действие помощника' }];
    if (method === 'POST' && rest.length === 0) return [201, { id: server.create(input) }];
    const id = String(rest[0]);
    if (rest[1] === 'stage') {
      server.setStage(id, input.stage as PrepStage);
      return [204, undefined];
    }
    if (rest[1] === 'items' && method === 'POST') {
      return [201, { id: server.addItem(id, String(input.text)) }];
    }
    if (rest[1] === 'items' && rest[2]) {
      server.toggle(id, rest[2], Boolean(input.done));
      return [204, undefined];
    }
    if (rest[1] === 'requests' && rest[3] === 'received') {
      server.receive(id, String(rest[2]), (input.received_on as string | null) ?? null);
      return [204, undefined];
    }
    return [404, { detail: `нет пути ${method} ${path}` }];
  } catch (error) {
    return [422, { detail: error instanceof Error ? error.message : String(error) }];
  }
}
