/**
 * Правила сервера «Взаимодействия» в памяти — те же, что считает настоящий: состояние
 * и ступень письма, скорость ответа (только при пяти письмах), «спящие» соглашения, ответы
 * четырёх вопросов и их списки. Главное обещание — одно вычисление на число и его список.
 */

import { describe, expect, it } from 'vitest';

import { FakeInteraction } from './test-server';
import type { QuestionAnswer } from './model';

const NOW = new Date('2026-10-01T07:00:00Z');

function server() {
  return new FakeInteraction(() => NOW);
}

function answer<K extends QuestionAnswer['key']>(
  ijro: FakeInteraction,
  key: K,
): Extract<QuestionAnswer, { key: K }> {
  const found = ijro.view().questions.find((each) => each.key === key);
  if (!found) throw new Error(key);
  return found as Extract<QuestionAnswer, { key: K }>;
}

describe('письма', () => {
  it('состояние: исходящее без ответа ждёт, входящее без ответа — за нами', () => {
    const view = server().view();
    const byId = new Map(view.letters.map((each) => [each.id, each]));
    expect(byId.get('l-trans-6')?.state).toBe('waiting_reply');
    expect(byId.get('l-eco-in-1')?.state).toBe('to_answer');
    expect(byId.get('l-eco-1')?.state).toBe('answered');
  });

  it('ступени: просроченный попрошенный срок — ждём чужих, без срока — после порога', () => {
    const byId = new Map(
      server()
        .view()
        .letters.map((each) => [each.id, each]),
    );
    expect(byId.get('l-trans-6')).toMatchObject({ step: 'blocked_by_others', deviation: 19 });
    expect(byId.get('l-samarkand-1')).toMatchObject({ step: 'blocked_by_others', deviation: 38 });
    expect(byId.get('l-trans-7')?.step).toBeNull();
    expect(byId.get('l-digital-in-1')).toMatchObject({ step: 'overdue', deviation: 2 });
    expect(byId.get('l-center-in-1')).toMatchObject({ step: 'burning', deviation: 2 });
  });

  it('порядок — лестница: просроченное выше горящего, горящее выше ждущего чужих', () => {
    const steps = server()
      .view()
      .letters.map((each) => each.step)
      .filter(Boolean);
    expect(steps.indexOf('overdue')).toBeLessThan(steps.indexOf('burning'));
    expect(steps.lastIndexOf('burning')).toBeLessThan(steps.indexOf('blocked_by_others'));
  });

  it('ответ получен — письмо уходит из «кто не отвечает»', () => {
    const ijro = server();
    const before = answer(ijro, 'not_answering');
    ijro.answer('l-trans-6', { on: '2026-10-01', number: '11-1020' });
    const after = answer(ijro, 'not_answering');
    expect(after.count).toBe(before.count - 1);
    expect(after.rows).not.toContain('l-trans-6');
  });

  it('оценивается только полученный ответ на наше письмо', () => {
    const ijro = server();
    expect(() => ijro.rate('l-eco-in-1', 'formal')).toThrow();
    ijro.rate('l-eco-4', 'off_topic');
    expect(ijro.view().letters.find((each) => each.id === 'l-eco-4')?.rating).toBe('off_topic');
  });
});

describe('вопросы', () => {
  it('четыре ответа в порядке экрана, списки — те же строки', () => {
    const ijro = server();
    const view = ijro.view();
    expect(view.questions.map((each) => each.key)).toEqual([
      'not_answering',
      'to_answer',
      'speed',
      'sleeping',
    ]);
    const waiting = answer(ijro, 'not_answering');
    expect(waiting.count).toBe(waiting.rows.length);
    expect(waiting.organizations.reduce((sum, each) => sum + each.count, 0)).toBe(waiting.count);
  });

  it('скорость — только у организаций с пятью ответами и больше (ТЗ 4)', () => {
    const ijro = server();
    const speed = answer(ijro, 'speed');
    expect(speed.measured.map((each) => each.organization.id)).toEqual(['o-trans', 'o-eco']);
    expect(speed.measured.every((each) => each.letters >= 5)).toBe(true);
    expect(speed.little_data).toBe(3);
    const digital = ijro.view().organizations.find((each) => each.id === 'o-digital');
    expect(digital?.speed).toEqual({ letters: 1, median_days: null });
  });

  it('медиана, а не среднее: Минэкологии отвечает за 10 дн', () => {
    const eco = server()
      .view()
      .organizations.find((each) => each.id === 'o-eco');
    expect(eco?.speed).toEqual({ letters: 6, median_days: 10 });
  });

  it('спящие соглашения — без движения больше 90 дней; шаг будит', () => {
    const ijro = server();
    expect(answer(ijro, 'sleeping').rows.sort()).toEqual(['g-trans', 'g-unoosa']);
    ijro.setNextStep('g-trans', { next_step: 'Созвониться с Минтрансом', next_step_on: null });
    expect(answer(ijro, 'sleeping').rows).toEqual(['g-unoosa']);
  });

  it('просроченный следующий шаг соглашения — просрочено', () => {
    const telecom = server()
      .view()
      .agreements.find((each) => each.id === 'g-telecom');
    expect(telecom).toMatchObject({ step: 'overdue', deviation: 5, sleeping: false });
  });
});

describe('карточка организации', () => {
  it('собирает письма, соглашения, поручения и проекты (ТЗ 11)', () => {
    const card = server().organization('o-eco');
    expect(card.letters).toHaveLength(8);
    expect(card.agreements.map((each) => each.id)).toEqual(['g-eco']);
    expect(card.ijro).toHaveLength(2);
    expect(card.projects).toHaveLength(1);
    expect(card.ratings).toEqual({ substance: 3, formal: 1, off_topic: 0 });
  });
});
