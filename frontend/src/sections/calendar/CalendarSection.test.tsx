/**
 * Экран «Календарь»: месяц сеткой с горячими днями и выбранным днём, «где неделя
 * перегружена?» как переход к дню, источники дат и скрытое фильтром, годовой цикл — лист с
 * датами, список циклов, новая запись с датами до записи и отмена; телефон — список по дням
 * без сетки, горячий день за концом списка.
 *
 * Данные — вымышленный сервер `demo.ts`; сеть подменена только для `/api/me`. День
 * закреплён: 28.09.2026, понедельник.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { CalendarSection } from './CalendarSection';
import { demoCalendar } from './demo';

const NOW = new Date('2026-09-28T07:00:00Z');

function user(role: 'leader' | 'assistant'): CurrentUser {
  return {
    id: `u-${role}`,
    full_name: role,
    role,
    locale: 'ru',
    timezone: 'Asia/Tashkent',
    can_write: role === 'assistant',
  };
}

function serve(role: 'leader' | 'assistant' = 'assistant') {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const found = path === '/api/me';
    return Promise.resolve({
      ok: found,
      status: found ? 200 : 404,
      statusText: '',
      json: () => Promise.resolve(found ? user(role) : { detail: `нет подмены ${path}` }),
    } as unknown as Response);
  });
}

function renderCalendar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CalendarSection />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
  demoCalendar.reset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// Сетка месяца — 35 клеток-кнопок с сотней дат, и каждое касание перерисовывает её целиком.
// Отдельно сценарий идёт за секунду-две, а в полном прогоне, когда файлы тестов идут
// параллельно, jsdom не укладывался в пять секунд по умолчанию. Поиск по роли в таком
// дереве занимает сотни миллисекунд, и за секунду ожидания `findBy…` успевал проверить
// экран раз-другой — до следующего ответа. Сроки — с запасом, а не повод ускорять экран.
beforeAll(() => configure({ asyncUtilTimeout: 5_000 }));
afterAll(() => configure({ asyncUtilTimeout: 1_000 }));

describe('Календарь', { timeout: 20_000 }, () => {
  it('ноутбук: месяц сеткой, горячие дни и сегодняшний день рядом', async () => {
    serve();
    renderCalendar();

    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Сентябрь 2026' })).toBeInTheDocument();
    expect(screen.getByText('Горячих дней: 3')).toBeInTheDocument();
    // Сегодня выбран и горячий: слова, а не только цвет.
    expect(screen.getByRole('heading', { name: 'Пн, 28 сентября' })).toBeInTheDocument();
    expect(screen.getByText('Горячий день: 3 срока: веха и 2 задачи')).toBeInTheDocument();
    // Срок прошёл — сверху сегодняшнего дня, свёрнуто.
    expect(screen.getByRole('button', { name: 'Срок прошёл, не закрыто: 5' })).toBeInTheDocument();
  });

  it('горячий день из карточки открывает свой месяц и день', async () => {
    serve();
    renderCalendar();
    await screen.findByText('Горячих дней: 3');

    fireEvent.click(screen.getByRole('button', { name: /^Вс, 18 октября/ }));
    expect(await screen.findByRole('region', { name: 'Октябрь 2026' })).toBeInTheDocument();
    const day = screen.getByRole('heading', { name: 'Вс, 18 октября' }).closest('section')!;
    expect(await within(day).findByText('Интеграция с геопорталом')).toBeInTheDocument();
  });

  it('месяцы листаются с выбранным днём, «сегодня» возвращает', async () => {
    serve();
    renderCalendar();
    await screen.findByRole('region', { name: 'Сентябрь 2026' });

    fireEvent.click(screen.getByRole('button', { name: 'Следующий месяц' }));
    fireEvent.click(screen.getByRole('button', { name: 'Следующий месяц' }));
    expect(await screen.findByRole('region', { name: 'Ноябрь 2026' })).toBeInTheDocument();
    // Справа — день ноября, а не сегодняшний со «сроков нет»; ответ карточки прежний.
    expect(await screen.findByRole('heading', { name: 'Вс, 1 ноября' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Пн, 28 сентября' })).not.toBeInTheDocument();
    expect(screen.getByText('Горячих дней: 3')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Сегодня' }));
    expect(await screen.findByRole('region', { name: 'Сентябрь 2026' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Пн, 28 сентября' })).toBeInTheDocument();
  });

  it('источник выключается — его дат нет ни в сетке, ни в дне', async () => {
    serve();
    renderCalendar();
    await screen.findByRole('heading', { name: 'Пн, 28 сентября' });
    expect(screen.getAllByText('Отбор участников пилота с Минсельхозом').length).toBeGreaterThan(0);

    const tasks = screen.getByRole('button', { name: 'Задачи' });
    fireEvent.click(tasks);
    expect(tasks).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByText('Отбор участников пилота с Минсельхозом')).not.toBeInTheDocument();
    // Источники блока 2 названы, чтобы их отсутствие не читалось как «ничего нет».
    expect(screen.getByText(/Поручения Ижро, письма, соглашения/)).toBeInTheDocument();

    // Горячий день считается по всем источникам — скрытое названо, и его можно вернуть.
    const day = screen.getByRole('heading', { name: 'Пн, 28 сентября' }).closest('section')!;
    expect(within(day).getByText('Скрыто фильтром: 3')).toBeInTheDocument();
    fireEvent.click(within(day).getByRole('button', { name: 'Показать всё' }));
    expect(tasks).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByText('Отбор участников пилота с Минсельхозом').length).toBeGreaterThan(0);
  });

  it('годовой цикл: правило, даты на год вперёд и отмена', async () => {
    serve('assistant');
    renderCalendar();
    await screen.findByRole('region', { name: 'Сентябрь 2026' });
    fireEvent.click(screen.getByRole('button', { name: 'Следующий месяц' }));
    fireEvent.click(await screen.findByRole('button', { name: /^Пн, 5 октября/ }));
    fireEvent.click(
      screen.getByRole('button', { name: /Сведения в Кабмин по программе космического/ }),
    );

    const sheet = screen.getByRole('dialog', { name: 'Годовой цикл' });
    expect(await within(sheet).findByText('ежеквартально, 5-го числа')).toBeInTheDocument();
    expect(within(sheet).getByText('05.10.2026')).toBeInTheDocument();
    expect(within(sheet).getByText('05.07.2027')).toBeInTheDocument();

    fireEvent.click(within(sheet).getByRole('button', { name: 'Отменить цикл' }));
    fireEvent.click(within(sheet).getByRole('button', { name: 'Да, отменить' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByRole('status')).toHaveTextContent('Цикл отменён');
    expect(
      screen.queryByRole('button', { name: /Сведения в Кабмин по программе космического/ }),
    ).not.toBeInTheDocument();
  });

  it('новый цикл: даты видны до записи, после — в календаре', async () => {
    serve('assistant');
    renderCalendar();
    fireEvent.click(await screen.findByRole('button', { name: 'Новый годовой цикл' }));

    const form = screen.getByRole('dialog', { name: 'Новый годовой цикл' });
    fireEvent.change(within(form).getByLabelText('Название'), {
      target: { value: 'Отчёт по субплатформам' },
    });
    fireEvent.change(within(form).getByLabelText('Месяц'), { target: { value: '10' } });
    // Стёртое число остаётся пустым, а не становится единицей: «15» набирается как «15».
    const day = within(form).getByLabelText('Число');
    fireEvent.change(day, { target: { value: '' } });
    expect(day).toHaveValue('');
    expect(within(form).getByText('Число — от 1 до 31.')).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: 'Завести цикл' })).toBeDisabled();
    fireEvent.change(day, { target: { value: '15' } });
    expect(await within(form).findByText('15.10.2026')).toBeInTheDocument();

    fireEvent.click(within(form).getByRole('button', { name: 'Завести цикл' }));
    const sheet = await screen.findByRole('dialog', { name: 'Годовой цикл' });
    expect(await within(sheet).findByText('Отчёт по субплатформам')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Цикл заведён: Отчёт по субплатформам');
  });

  it('«раз в несколько лет» без дат на год вперёд — ближайшая дата, а не «числа нет»', async () => {
    serve('assistant');
    renderCalendar();
    fireEvent.click(await screen.findByRole('button', { name: 'Новый годовой цикл' }));
    const form = screen.getByRole('dialog', { name: 'Новый годовой цикл' });
    fireEvent.click(within(form).getByLabelText('Раз в несколько лет'));
    expect(
      await within(form).findByText('За год вперёд дат нет: ближайшая — 20.01.2029.'),
    ).toBeInTheDocument();

    // 30 февраля нет ни в одном году — такой цикл не записывается.
    fireEvent.click(within(form).getByLabelText('Ежегодно'));
    fireEvent.change(within(form).getByLabelText('Месяц'), { target: { value: '2' } });
    fireEvent.change(within(form).getByLabelText('Число'), { target: { value: '30' } });
    fireEvent.change(within(form).getByLabelText('Название'), { target: { value: 'Опечатка' } });
    expect(await within(form).findByText(/Такого дня нет ни в одном году/)).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: 'Завести цикл' })).toBeDisabled();
  });

  it('список циклов: и цикл без дат на год вперёд можно открыть', async () => {
    serve('leader');
    renderCalendar();
    fireEvent.click(await screen.findByRole('button', { name: 'Список циклов' }));
    const list = screen.getByRole('dialog', { name: 'Годовые циклы' });
    const row = await within(list).findByRole('button', {
      name: /Переаттестация операторов станции приёма/,
    });
    expect(row).toHaveTextContent('ближайшая — 15.11.2027');

    fireEvent.click(row);
    const sheet = await screen.findByRole('dialog', { name: 'Годовой цикл' });
    expect(
      await within(sheet).findByText('За год вперёд дат нет: ближайшая — 15.11.2027.'),
    ).toBeInTheDocument();
    // Руководитель смотрит: отменить нечем.
    expect(within(sheet).queryByRole('button', { name: 'Отменить цикл' })).not.toBeInTheDocument();
  });

  it('руководитель смотрит: цикл не заводит и не отменяет', async () => {
    serve('leader');
    renderCalendar();
    await screen.findByRole('region', { name: 'Сентябрь 2026' });
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Новый годовой цикл' })).not.toBeInTheDocument(),
    );
  });

  it('касание задачи — что откроется после утверждения', async () => {
    serve();
    renderCalendar();
    await screen.findByRole('heading', { name: 'Пн, 28 сентября' });
    const day = screen.getByRole('heading', { name: 'Пн, 28 сентября' }).closest('section')!;
    fireEvent.click(within(day).getByRole('button', { name: /Отбор участников пилота/ }));
    expect(screen.getByRole('status')).toHaveTextContent('карточка задачи');
  });

  it('телефон: ближайшие дни списком, без сетки', async () => {
    setViewport({ width: 390 });
    serve();
    renderCalendar();

    expect(await screen.findByRole('region', { name: 'Ближайшие дни' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Сентябрь 2026' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Пн, 28 сентября' })).toBeInTheDocument();
    // Две недели: 8 октября — горячий день — в списке, 13-е — уже нет.
    expect(screen.getByRole('region', { name: 'Чт, 8 октября' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Вт, 13 октября' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Показать ещё две недели' }));
    expect(await screen.findByRole('region', { name: 'Вт, 13 октября' })).toBeInTheDocument();
  });

  it('телефон: горячий день за концом списка — список дорастает до него', async () => {
    setViewport({ width: 390 });
    serve();
    renderCalendar();
    await screen.findByRole('region', { name: 'Ближайшие дни' });
    expect(screen.queryByRole('region', { name: 'Вс, 18 октября' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Вс, 18 октября/ }));
    expect(await screen.findByRole('region', { name: 'Вс, 18 октября' })).toBeInTheDocument();
  });

  it('день — с сервера: часы телефона спешат через полночь, список не зацикливается', async () => {
    setViewport({ width: 390 });
    // 00:01 29 сентября по часам телефона, а у сервера ещё 23:58 28-го.
    vi.setSystemTime(new Date('2026-09-28T19:01:00Z'));
    let serverNow = '2026-09-28T18:58:00Z';
    const view = demoCalendar.view.bind(demoCalendar);
    vi.spyOn(demoCalendar, 'view').mockImplementation((range) => ({
      ...view(range),
      as_of: serverNow,
    }));
    serve();
    const client = renderCalendar();
    expect(await screen.findByRole('region', { name: 'Пн, 28 сентября' })).toBeInTheDocument();

    // Полночь наступила и у сервера: под прежним диапазоном в кэше лежит ответ с 28-м.
    vi.setSystemTime(new Date('2026-09-28T19:01:30Z'));
    serverNow = '2026-09-28T19:00:30Z';
    await act(() => client.invalidateQueries({ queryKey: ['calendar'] }));
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: 'Пн, 28 сентября' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('region', { name: 'Ближайшие дни' })).toBeInTheDocument();
  });

  it('монитор: сетка и колонка рядом', async () => {
    setViewport({ width: 2560 });
    serve();
    renderCalendar();
    expect(await screen.findByRole('region', { name: 'Сентябрь 2026' })).toBeInTheDocument();
    expect(screen.getByText('Горячих дней: 3')).toBeInTheDocument();
  });
});
