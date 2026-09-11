/**
 * Мобильный каркас (ORB-079).
 *
 * Проверять размеры в пикселях в jsdom нельзя: он не выполняет вёрстку, и любой
 * `getBoundingClientRect` вернёт нули. Поэтому здесь проверяется то, что проверяемо без
 * браузера и что ломается чаще всего:
 *
 * - навигация на телефоне **существует** — до ORB-079 боковое меню ниже 640 px просто
 *   исчезало, и с экрана нельзя было никуда уйти;
 *
 * - правило целей нажатия живёт в токенах и берётся оттуда, а не переписывается числом
 *   в каждом экране: правило, повторённое в семи местах, в восьмом забудут;
 *
 * - таблица на узком экране становится карточками, а не прокручиваемой простынёй.
 *
 * Размеры в пикселях проверены вживую на 375 px: горизонтальная прокрутка страницы 0,
 * наименьшая цель нажатия 64×60. Числа записаны в карточке тикета — здесь их повторять
 * нечем, и делать вид, что jsdom их меряет, не стоит.
 */

import { render, screen, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { routes } from '../app/router';
import { NAV_ITEMS } from '../app/routes';
import { WithSession } from '../testing/WithSession';

function css(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
}

const LAYOUT = css('./layout.module.css');
const TOKENS = css('../styles/tokens.css');
const PROJECTS = css('../features/projects/projects.module.css');
const TASKS = css('../features/tasks/tasks.module.css');
const PAGES = css('../pages/pages.module.css');

function renderApp(path = '/projects') {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <WithSession>
      <RouterProvider router={router} />
    </WithSession>,
  );
}

describe('навигация на телефоне', () => {
  it('существует и ведёт во все разделы', () => {
    renderApp();

    const mobile = within(screen.getByRole('navigation', { name: 'Разделы системы' }));

    expect(mobile.getAllByRole('link')).toHaveLength(NAV_ITEMS.length);
    expect(mobile.getByRole('link', { name: /Проекты/ })).toBeInTheDocument();
    expect(mobile.getByRole('link', { name: /Администрирование/ })).toBeInTheDocument();
  });

  it('ничего не спрятано за «ещё»: разделов столько же, сколько в боковом меню', () => {
    renderApp();

    const sidebar = within(screen.getByRole('navigation', { name: 'Разделы' }));
    const mobile = within(screen.getByRole('navigation', { name: 'Разделы системы' }));

    expect(mobile.getAllByRole('link')).toHaveLength(sidebar.getAllByRole('link').length);
  });

  it('три ориентира навигации названы по-разному', () => {
    renderApp();

    const names = screen
      .getAllByRole('navigation')
      .map((element) => element.getAttribute('aria-label'));

    expect(new Set(names).size).toBe(names.length);
  });

  it('полоса разделов прокручивается, а не обрезается', () => {
    expect(LAYOUT).toMatch(/\.bottomNav\s*\{[^}]*overflow-x:\s*auto/s);
  });
});

describe('правило целей нажатия', () => {
  it('задано в токенах, а не числом по месту', () => {
    expect(TOKENS).toMatch(/--tap-target-min:\s*44px/);
  });

  it('экраны берут его из токенов и не переопределяют своим числом', () => {
    for (const [name, source] of [
      ['layout', LAYOUT],
      ['projects', PROJECTS],
      ['tasks', TASKS],
      ['pages', PAGES],
    ] as const) {
      expect(source, `${name}: цель нажатия задана числом мимо токена`).not.toMatch(
        /min-height:\s*4[0-9]px/,
      );
    }
  });

  it('нижняя панель и поля ввода подтянуты до правила', () => {
    expect(LAYOUT).toMatch(/\.bottomLink\s*\{[^}]*min-height:\s*var\(--tap-target-min\)/s);
    expect(PAGES).toMatch(/\.input\s*\{[^}]*min-height:\s*var\(--tap-target-min\)/s);
    expect(PAGES).toMatch(/\.primaryButton\s*\{[^}]*min-height:\s*var\(--tap-target-min\)/s);
  });
});

describe('узкий экран', () => {
  it('таблица портфеля становится карточками, а не прокручиваемой простынёй', () => {
    const narrow = PROJECTS.slice(PROJECTS.indexOf('@media (max-width: 640px)'));

    expect(narrow).toMatch(/\.table tr\s*\{[^}]*display:\s*flex/s);
    expect(narrow).toMatch(/\.tableWrap\s*\{[^}]*overflow-x:\s*visible/s);
  });

  it('заголовки столбцов убраны с глаз, но оставлены программам чтения с экрана', () => {
    const narrow = PROJECTS.slice(PROJECTS.indexOf('@media (max-width: 640px)'));

    expect(narrow).toMatch(/\.table thead\s*\{[^}]*clip-path/s);
    expect(narrow).not.toMatch(/\.table thead\s*\{[^}]*display:\s*none/s);
  });

  it('сетка оболочки умеет сжиматься: колонка не шире своего окна', () => {
    // Найдено замером: без `minmax(0, 1fr)` длинная строка в шапке уводила страницу
    // за край экрана на 726 px.
    expect(LAYOUT).toMatch(/grid-template-columns:\s*var\(--layout-sidebar-width\)\s*minmax\(0/);
  });
});

describe('база задач на узком экране', () => {
  const narrow = TASKS.slice(TASKS.indexOf('@media (max-width: 640px)'));

  it('таблица становится карточками', () => {
    expect(narrow).toMatch(/\.table tr\s*\{[^}]*display:\s*flex/s);
    expect(narrow).toMatch(/\.tableWrap\s*\{[^}]*overflow-x:\s*visible/s);
  });

  it('заливка просрочки принадлежит карточке и переспоривает фон строки', () => {
    // Найдено вживую: пока правило было записано как `.overdue`, его перебивал
    // `.table tr` — более сильный селектор, — и просроченная карточка оставалась белой.
    // Порядок записи тут ни при чём, решает специфичность, и решает молча.
    expect(narrow).toMatch(/\.table tr\.overdue\s*\{[^}]*background:/s);
    expect(narrow).toMatch(/\.table tr\.overdue\s*\{[^}]*border-left:/s);
  });

  it('ячейки просроченной карточки не красятся по отдельности', () => {
    // По ячейкам заливка ложилась прорехами: между ними в карточке есть промежутки.
    expect(narrow).toMatch(/\.overdue td[^{]*\{[^}]*background:\s*transparent/s);
  });
});

describe('название колонки и заголовок страницы — разные вещи', () => {
  it('ячейки таблицы задач названы отдельно от заголовка', () => {
    // Пока класс ячейки брался по имени колонки, `title` совпадал с `.title` заголовка
    // страницы, и в таблицу протекал его кегль: названия набирались в полтора раза
    // крупнее, каждая строка переносилась на две, и на экран влезало вдвое меньше задач.
    expect(TASKS).toMatch(/\.cellTitle\s*\{/);
    expect(TASKS).not.toMatch(/\.table td\.title\s*\{/);
  });
});
