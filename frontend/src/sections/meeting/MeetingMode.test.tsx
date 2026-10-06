/**
 * Совещание — обещания экрана.
 *
 * Слайд повестки — тот же ответ, что на экране раздела: функции ответа общие; режим
 * «Совещание» проходит повестку стрелками и выходит по Esc, ничего служебного не показывая
 * (критерий 2 блока 3). Пока разделы не пришли — загрузка, а не часть повестки; раздел без
 * данных — слайд «не удалось»; клавиатура не уходит за диалог.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import i18next from 'i18next';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { FakeIdeas } from '@/sections/ideas/test-server';
import { FakeInteraction } from '@/sections/interaction/test-server';
import { answerText as interactionAnswer } from '@/sections/interaction/text';
import { FakeReports } from '@/sections/reports/test-server';
import { answerText as reportsAnswer } from '@/sections/reports/text';

import { failedSlide, ideasSlide, interactionSlide, reportsSlide, type Slide } from './agenda';
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
    lines: [{ key: 'tasks:t-1', text: 'Просрочено — Приёмка опытного образца' }],
    freshness: 'на 05.10',
    empty: false,
    failed: false,
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
    failed: false,
  },
];

/** Что отдаёт подменённая повестка: тест меняет её и перерисовывает экран. */
const agenda = vi.hoisted(() => ({ slides: [] as Slide[], pending: false }));

const navigate = vi.fn(() => Promise.resolve());
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigate }));
vi.mock('./useAgenda', () => ({ useAgenda: () => agenda }));

beforeEach(() => {
  agenda.slides = SLIDES;
  agenda.pending = false;
});

afterEach(() => {
  cleanup();
  navigate.mockClear();
});

const onClose = () => undefined;

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
    // Старшая — первой строкой; ключ строки — идея, а не текст.
    expect(ideas?.lines[0]?.text).toMatch(/^Открытый каталог снимков/);
    expect(new Set(ideas?.lines.map((line) => line.key)).size).toBe(ideas?.lines.length);
  });

  it('один вопрос на экран: стрелки листают, Esc выходит', () => {
    const close = vi.fn();
    render(<MeetingMode onClose={close} />);

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
    expect(close).toHaveBeenCalled();
  });

  it('«Открыть раздел» выходит из совещания и ведёт в раздел слайда', () => {
    const close = vi.fn();
    render(<MeetingMode onClose={close} />);
    fireEvent.keyDown(window, { key: ' ' });
    fireEvent.click(screen.getByRole('button', { name: 'Открыть раздел' }));
    expect(close).toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith({ to: '/ideas' });
  });

  it('пока разделы не пришли — загрузка, а не часть повестки', () => {
    // Пульт уже в кэше, остальные разделы ещё в пути.
    agenda.slides = [SLIDES[0]!];
    agenda.pending = true;
    const { rerender } = render(<MeetingMode onClose={onClose} />);

    expect(screen.getByRole('status')).toHaveTextContent('Загружаем');
    expect(screen.queryByRole('heading', { name: 'Что требует внимания?' })).toBeNull();
    expect(screen.queryByText('1 / 1')).toBeNull();
    // Листать пока нечего: нажатие не сдвигает невидимую позицию.
    fireEvent.keyDown(window, { key: 'ArrowRight' });

    agenda.slides = SLIDES;
    agenda.pending = false;
    rerender(<MeetingMode onClose={onClose} />);

    expect(screen.getByRole('heading', { name: 'Что требует внимания?' })).toBeVisible();
    expect(screen.getByText('1 / 2')).toBeVisible();
  });

  it('повестка изменилась под открытым совещанием — экран на том же вопросе', () => {
    const { rerender } = render(<MeetingMode onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(screen.getByText('2 / 2')).toBeVisible();

    // Перед идеями появился вопрос Ижро: «второй вопрос» теперь другой, а смотрят идеи.
    agenda.slides = [SLIDES[0]!, failedSlide(t, 'ijro', 'Сервер ответил 500'), SLIDES[1]!];
    rerender(<MeetingMode onClose={onClose} />);

    expect(screen.getByRole('heading', { name: 'Что ждёт моего «да»?' })).toBeVisible();
    expect(screen.getByText('3 / 3')).toBeVisible();
  });

  it('раздел без данных — слайд «не удалось» со ссылкой в раздел, а не пропуск', () => {
    agenda.slides = [SLIDES[0]!, failedSlide(t, 'ijro', 'Сервер ответил 500'), SLIDES[1]!];
    render(<MeetingMode onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'ArrowRight' });

    expect(screen.getByText('2 / 3')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Что горит и что просрочено?' })).toBeVisible();
    expect(screen.getByText('Не удалось получить данные раздела')).toBeVisible();
    expect(screen.getByText('Сервер ответил 500')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть раздел' }));
    expect(navigate).toHaveBeenCalledWith({ to: '/ijro' });
  });

  it('фокус — в диалоге, Tab не уходит наружу, после выхода — на кнопке «Совещание»', async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Совещание
          </button>
          {open ? <MeetingMode onClose={() => setOpen(false)} /> : null}
        </>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Совещание' });
    opener.focus();
    fireEvent.click(opener);

    const dialog = screen.getByRole('dialog', { name: 'Совещание: один вопрос на экран' });
    expect(dialog).toHaveFocus();

    const inside = within(dialog)
      .getAllByRole('button')
      .filter((button) => !button.hasAttribute('disabled'));
    const first = inside[0]!;
    const end = inside.at(-1)!;
    fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(end).toHaveFocus();
    fireEvent.keyDown(end, { key: 'Tab' });
    expect(first).toHaveFocus();

    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it('пробел на кнопке нажимает кнопку, а не листает', () => {
    render(<MeetingMode onClose={onClose} />);
    const exit = screen.getByRole('button', { name: 'Выйти из совещания' });
    exit.focus();
    fireEvent.keyDown(exit, { key: ' ' });
    expect(screen.getByText('1 / 2')).toBeVisible();

    // На самом диалоге пробел — пульт презентации: листает.
    fireEvent.keyDown(screen.getByRole('dialog'), { key: ' ' });
    expect(screen.getByText('2 / 2')).toBeVisible();
  });
});
