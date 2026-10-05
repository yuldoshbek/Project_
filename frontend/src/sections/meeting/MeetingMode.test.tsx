/**
 * Совещание — обещания экрана.
 *
 * Слайд повестки — тот же ответ, что на экране раздела: функции ответа общие; режим
 * «Совещание» проходит повестку стрелками и выходит по Esc, ничего служебного не показывая
 * (критерий 2 блока 3).
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import i18next from 'i18next';
import { afterEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { FakeIdeas } from '@/sections/ideas/test-server';
import { FakeInteraction } from '@/sections/interaction/test-server';
import { answerText as interactionAnswer } from '@/sections/interaction/text';
import { FakeReports } from '@/sections/reports/test-server';
import { answerText as reportsAnswer } from '@/sections/reports/text';

import { ideasSlide, interactionSlide, reportsSlide, type Slide } from './agenda';
import MeetingMode from './MeetingMode';

const t = i18next.t.bind(i18next);

const SLIDES: Slide[] = [
  {
    key: 'pult',
    section: 'pult',
    path: '/',
    question: 'Что требует внимания?',
    main: 'Ждёт решения 6 · Просрочено 23',
    detail: null,
    lines: ['Просрочено — Приёмка опытного образца'],
    freshness: 'на 05.10',
    empty: false,
  },
  {
    key: 'ideas',
    section: 'ideas',
    path: '/ideas',
    question: 'Что ждёт моего «да»?',
    main: '2 идеи ждут вашего «да»',
    detail: 'дольше всех — 9 дней',
    lines: [],
    freshness: 'на 05.10',
    empty: false,
  },
];

const navigate = vi.fn(() => Promise.resolve());
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigate }));
vi.mock('./useAgenda', () => ({ useAgenda: () => ({ slides: SLIDES, pending: false }) }));

afterEach(() => {
  cleanup();
  navigate.mockClear();
});

describe('Совещание', () => {
  it('слайд — тот же ответ, что на экране раздела', () => {
    const reports = new FakeReports().view();
    const readiness = reports.questions.find((each) => each.key === 'readiness')!;
    expect(reportsSlide(t, reports)?.main).toBe(reportsAnswer(t, readiness).main);

    const interaction = new FakeInteraction().view();
    const silent = interaction.questions.find((each) => each.key === 'not_answering')!;
    expect(interactionSlide(t, interaction)?.main).toBe(interactionAnswer(t, silent).main);

    const ideas = ideasSlide(t, new FakeIdeas().view());
    expect(ideas?.main).toBe('2 идеи ждут вашего «да»');
    // Старшая — первой строкой.
    expect(ideas?.lines[0]).toMatch(/^Открытый каталог снимков/);
  });

  it('один вопрос на экран: стрелки листают, Esc выходит', () => {
    const onClose = vi.fn();
    render(<MeetingMode onClose={onClose} />);

    expect(screen.getByRole('dialog', { name: 'Совещание: один вопрос на экран' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Что требует внимания?' })).toBeVisible();
    expect(screen.queryByText('Что ждёт моего «да»?')).toBeNull();
    expect(screen.getByText('1 / 2')).toBeVisible();

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(screen.getByRole('heading', { name: 'Что ждёт моего «да»?' })).toBeVisible();
    expect(screen.getByText('2 / 2')).toBeVisible();
    // Дальше последнего не листается.
    fireEvent.keyDown(window, { key: 'PageDown' });
    expect(screen.getByText('2 / 2')).toBeVisible();

    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(screen.getByRole('heading', { name: 'Что требует внимания?' })).toBeVisible();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('«Открыть раздел» выходит из совещания и ведёт в раздел слайда', () => {
    const onClose = vi.fn();
    render(<MeetingMode onClose={onClose} />);
    fireEvent.keyDown(window, { key: ' ' });
    fireEvent.click(screen.getByRole('button', { name: 'Открыть раздел' }));
    expect(onClose).toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith({ to: '/ideas' });
  });
});
