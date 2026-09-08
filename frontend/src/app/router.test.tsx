import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { routes } from './router';

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

describe('каркас приложения', () => {
  it('на корневом адресе показывает дашборд', () => {
    renderAt('/');
    expect(screen.getByRole('heading', { name: 'Дашборд' })).toBeInTheDocument();
  });

  it('переход по боковому меню меняет экран и хлебные крошки', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.click(screen.getByRole('link', { name: 'Проекты' }));

    expect(screen.getByRole('heading', { name: 'Проекты' })).toBeInTheDocument();
    expect(screen.getByText('Проекты', { selector: '[aria-current="page"]' })).toBeInTheDocument();
  });

  it('на неизвестном адресе показывает страницу «не найдено», а не пустой экран', () => {
    renderAt('/такого-раздела-нет');
    expect(screen.getByRole('heading', { name: 'Страница не найдена' })).toBeInTheDocument();
  });

  it('экран отказа в доступе объясняет, что делать дальше (сценарий U7)', () => {
    renderAt('/403');
    expect(screen.getByRole('heading', { name: 'Нет доступа' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'На дашборд' })).toBeInTheDocument();
  });

  it('каждый раздел из бокового меню открывается', async () => {
    const user = userEvent.setup();
    renderAt('/');

    for (const name of ['Сегодня', 'База задач', 'Календарь', 'Отчёты', 'Администрирование']) {
      await user.click(screen.getByRole('link', { name }));
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
  });
});
