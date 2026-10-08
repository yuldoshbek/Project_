/**
 * Повестка из ответов разделов: какой слайд даёт раздел, пока запрос идёт, когда он упал и
 * когда упал только фоновый опрос.
 *
 * Запросы разделов подменены на уровне их хуков: здесь проверяется сборка повестки, а не
 * сеть — сеть и формы ответов проверяют тесты разделов.
 */

import { cleanup, renderHook } from '@testing-library/react';
import i18next from 'i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CalendarView } from '@/sections/calendar/model';
import { FakeIdeas } from '@/sections/ideas/test-server';
import { FakeIjro } from '@/sections/ijro/test-server';
import { FakeInteraction } from '@/sections/interaction/test-server';
import type { PultView } from '@/sections/pult/model';
import { FakeReports } from '@/sections/reports/test-server';
import { ApiError } from '@/shared/api/client';

import { ijroSlide } from './agenda';
import { useAgenda } from './useAgenda';

const t = i18next.t.bind(i18next);

interface Source {
  data: unknown;
  isPending: boolean;
  isError: boolean;
  error: unknown;
}

const sources = vi.hoisted(() => ({}) as Record<string, Source>);

vi.mock('@/sections/pult/usePult', () => ({ usePult: () => sources.pult }));
vi.mock('@/sections/ijro/useIjro', () => ({ useIjro: () => sources.ijro }));
vi.mock('@/sections/reports/useReports', () => ({ useReports: () => sources.reports }));
vi.mock('@/sections/interaction/useInteraction', () => ({
  useInteraction: () => sources.interaction,
}));
vi.mock('@/sections/ideas/useIdeas', () => ({ useIdeas: () => sources.ideas }));
vi.mock('@/sections/calendar/useCalendar', () => ({ useCalendar: () => sources.calendar }));

const PULT = {
  as_of: '2026-10-05T07:00:00Z',
  rows: [],
  counts: { awaiting_decision: 0, overdue: 0, burning: 0, blocked_by_others: 0, silent: 0 },
  on_track: 4,
} as unknown as PultView;

const CALENDAR = { as_of: '2026-10-05T07:00:00Z', hot_ahead: [] } as unknown as CalendarView;

const answered = (data: unknown): Source => ({
  data,
  isPending: false,
  isError: false,
  error: null,
});
const loading: Source = { data: undefined, isPending: true, isError: false, error: null };
const failed = (error: unknown): Source => ({
  data: undefined,
  isPending: false,
  isError: true,
  error,
});

beforeEach(() => {
  sources.pult = answered(PULT);
  sources.ijro = answered(new FakeIjro().view());
  sources.reports = answered(new FakeReports().view());
  sources.interaction = answered(new FakeInteraction().view());
  sources.ideas = answered(new FakeIdeas().view());
  sources.calendar = answered(CALENDAR);
});

afterEach(cleanup);

const ORDER = ['pult', 'ijro', 'reports', 'interaction', 'ideas', 'calendar'];

describe('повестка', () => {
  it('все разделы ответили — шесть вопросов по порядку', () => {
    const { result } = renderHook(() => useAgenda());
    expect(result.current.pending).toBe(false);
    expect(result.current.slides.map((slide) => slide.key)).toEqual(ORDER);
  });

  it('упавший раздел остаётся в повестке слайдом «не удалось», а не пропадает', () => {
    sources.ijro = failed(new ApiError(500, 'Сервер ответил 500'));
    const { result } = renderHook(() => useAgenda());

    expect(result.current.pending).toBe(false);
    expect(result.current.slides.map((slide) => slide.key)).toEqual(ORDER);
    const ijro = result.current.slides[1]!;
    expect(ijro).toMatchObject({
      failed: true,
      path: '/ijro',
      main: 'Не удалось получить данные раздела',
      detail: 'Сервер ответил 500',
      freshness: null,
      lines: [],
    });
    // Вопрос тот же, что у слайда с ответом: пропуск ответа виден на своём месте.
    expect(ijro.question).toBe(ijroSlide(t, new FakeIjro().view())?.question);
  });

  it('упал только фоновый опрос — ответ по прежним данным, а не «не удалось»', () => {
    sources.ijro = {
      ...answered(new FakeIjro().view()),
      isError: true,
      error: new ApiError(502, 'Bad Gateway'),
    };
    const { result } = renderHook(() => useAgenda());
    expect(result.current.slides[1]).toMatchObject({ key: 'ijro', failed: false });
  });

  it('пока раздел в пути — повестка не готова', () => {
    sources.calendar = loading;
    const { result } = renderHook(() => useAgenda());
    expect(result.current.pending).toBe(true);
    expect(result.current.slides).toHaveLength(5);
  });
});
