/**
 * Пульт на вымышленных данных: порядок лестницы, решение в одно касание, отмена, вопрос
 * помощника, фильтр «кто держит».
 *
 * Вымышленный сервер (`demo.ts`) проверяется отдельно от экрана: его порядок — это
 * обещание, которое потом держит `GET /api/v1/pult`, и тест на него переедет к API вместе
 * с договором (`model.ts`).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';

import { DemoPult, demoPult } from './demo';
import { LADDER, rowKey } from './model';
import { PultSection } from './PultSection';

const LEADER: CurrentUser = {
  id: 'user-leader',
  full_name: 'Заместитель директора',
  role: 'leader',
  locale: 'ru',
  timezone: 'Asia/Tashkent',
  can_write: false,
};

function serveMe() {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: true,
    status: 200,
    statusText: '',
    json: () => Promise.resolve(LEADER),
  } as unknown as Response);
}

function renderPult() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PultSection />
    </QueryClientProvider>,
  );
}

/** Число на счётчике ступени — по подписи кнопки-фильтра. */
function counter(step: string): string {
  const button = screen.getByRole('button', { name: `Показать только: ${step}` });
  return within(button).getByText(/^\d+$/).textContent ?? '';
}

describe('вымышленный сервер Пульта', () => {
  it('держит порядок лестницы: ступени по ТЗ 4, внутри — что горит сильнее', () => {
    const view = new DemoPult().view();
    const ranks = view.rows.map((row) => LADDER.indexOf(row.step));
    expect(ranks).toEqual([...ranks].sort((a, b) => a - b));

    const burning = view.rows.filter((row) => row.step === 'burning').map((row) => row.deviation);
    expect(burning).toEqual([...burning].sort((a, b) => a - b));

    const overdue = view.rows.filter((row) => row.step === 'overdue').map((row) => row.deviation);
    expect(overdue).toEqual([...overdue].sort((a, b) => b - a));
  });

  it('считает ступени и «кто держит» по тем же строкам', () => {
    const view = new DemoPult().view();
    for (const step of LADDER) {
      expect(view.counts[step]).toBe(view.rows.filter((row) => row.step === step).length);
    }
    const heldRows = view.holders.reduce((sum, holder) => sum + holder.total, 0);
    expect(heldRows).toBe(view.rows.filter((row) => row.responsible).length);
  });

  it('решение закрывает вопрос, отмена возвращает его', () => {
    const pult = new DemoPult();
    const asked = pult.view().rows[0]!;
    expect(asked.step).toBe('awaiting_decision');

    pult.decide(rowKey(asked), 'approve');
    const answered = pult.view().rows.find((row) => row.entity_id === asked.entity_id);
    expect(answered?.step).not.toBe('awaiting_decision');
    expect(answered?.last_decision?.kind).toBe('approve');

    pult.undo(rowKey(asked));
    expect(pult.view().rows[0]?.entity_id).toBe(asked.entity_id);
  });

  it('вопрос помощника поднимает строку на верхнюю ступень', () => {
    const pult = new DemoPult();
    const silent = pult.view().rows.find((row) => row.step === 'silent')!;

    pult.ask(rowKey(silent), 'Нужно ваше решение');

    const lifted = pult.view().rows.find((row) => row.entity_id === silent.entity_id);
    expect(lifted?.step).toBe('awaiting_decision');
    expect(lifted?.question?.text).toBe('Нужно ваше решение');
  });
});

describe('экран Пульта', () => {
  beforeEach(() => {
    demoPult.reset();
    serveMe();
  });
  afterEach(() => vi.restoreAllMocks());

  it('говорит, что данные вымышленные', async () => {
    renderPult();
    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
  });

  it('решение в одно касание меняет лестницу, «Отменить» возвращает', async () => {
    renderPult();
    await screen.findByText('Согласование ТЗ на спутниковую группировку');
    expect(counter('Ждёт решения')).toBe('2');

    fireEvent.click(screen.getAllByRole('button', { name: 'Утвердить' })[0]!);

    await waitFor(() => expect(counter('Ждёт решения')).toBe('1'));
    const undo = screen.getByRole('button', { name: 'Отменить' });
    expect(screen.getByRole('status')).toHaveTextContent('Согласование ТЗ');

    fireEvent.click(undo);
    await waitFor(() => expect(counter('Ждёт решения')).toBe('2'));
  });

  it('помощник не решает за руководителя, а задаёт вопрос', async () => {
    renderPult();
    await screen.findByText('Согласование ТЗ на спутниковую группировку');

    fireEvent.click(screen.getByRole('button', { name: 'Помощник' }));

    expect(screen.queryByRole('button', { name: 'Утвердить' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Спросить' }).length).toBeGreaterThan(0);
  });

  it('касание человека в «Кто держит» оставляет в лестнице только его строки', async () => {
    renderPult();
    await screen.findByText('Согласование ТЗ на спутниковую группировку');

    fireEvent.click(screen.getByRole('button', { name: 'Показать строки: Турсунов Б.' }));

    expect(screen.getByText('Показано: Турсунов Б.')).toBeInTheDocument();
    expect(screen.getByText('Заказ услуги: аэрофотосъёмка Ферганской долины')).toBeInTheDocument();
    expect(
      screen.queryByText('Согласование ТЗ на спутниковую группировку'),
    ).not.toBeInTheDocument();
  });
});
