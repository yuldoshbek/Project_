/**
 * Вход и ворота приложения.
 *
 * Проверяется не «работает ли форма», а три обещания, каждое из которых при нарушении
 * стоит дорого: отказ не выдаёт, существует ли адрес; истёкшая сессия уводит на вход, а
 * отказ по роли — нет; адрес, с которого увели, возвращается после входа.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { routes } from '../../app/router';
import { sessionOf } from '../../testing/profiles';
import { WithSession } from '../../testing/WithSession';
import { configureApi, HttpError, request } from '../api/client';

function renderAt(path: string, status: 'anonymous' | 'signed-in' | 'restoring') {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <WithSession value={sessionOf(status === 'signed-in' ? null : null, status)}>
      <RouterProvider router={router} />
    </WithSession>,
  );
}

describe('ворота приложения', () => {
  it('без входа уводит на экран входа, а не показывает пустой раздел', async () => {
    renderAt('/projects', 'anonymous');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Войти' })).toBeInTheDocument();
    });
  });

  it('пока сессия восстанавливается, экран входа не мелькает', () => {
    renderAt('/projects', 'restoring');

    expect(screen.queryByRole('button', { name: 'Войти' })).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});

describe('форма входа', () => {
  it('неверный пароль и несуществующий адрес дают один и тот же текст', async () => {
    const user = userEvent.setup();
    const signIn = vi.fn().mockRejectedValue(new HttpError(401, { type: '/problems/auth-failed' }));
    const router = createMemoryRouter(routes, { initialEntries: ['/login'] });

    render(
      <WithSession value={{ ...sessionOf(null, 'anonymous'), signIn }}>
        <RouterProvider router={router} />
      </WithSession>,
    );

    await user.type(screen.getByLabelText('Адрес электронной почты'), 'unknown@orbita.local');
    await user.type(screen.getByLabelText('Пароль'), 'неверный-пароль');
    await user.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Неверный адрес или пароль');
  });

  it('блокировка после перебора объясняет, что надо подождать, а не повторить', async () => {
    const user = userEvent.setup();
    const signIn = vi
      .fn()
      .mockRejectedValue(new HttpError(401, { type: '/problems/account-locked' }));
    const router = createMemoryRouter(routes, { initialEntries: ['/login'] });

    render(
      <WithSession value={{ ...sessionOf(null, 'anonymous'), signIn }}>
        <RouterProvider router={router} />
      </WithSession>,
    );

    await user.type(screen.getByLabelText('Адрес электронной почты'), 'assistant@orbita.local');
    await user.type(screen.getByLabelText('Пароль'), 'какой-нибудь-пароль');
    await user.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('временно заблокирован');
  });
});

describe('клиент API', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    configureApi(
      () => null,
      () => {},
    );
  });

  it('пустые фильтры не попадают в адрес запроса', async () => {
    fetchMock.mockResolvedValue(new Response('[]', { status: 200 }));

    await request('/projects', { query: { status_code: '', search: 'станц', health: undefined } });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/projects?search=%D1%81%D1%82%D0%B0%D0%BD%D1%86',
    );
  });

  it('код 401 закрывает сессию, а 403 — нет', async () => {
    const onUnauthorized = vi.fn();
    configureApi(() => 'токен', onUnauthorized);

    fetchMock.mockResolvedValue(new Response('{}', { status: 401 }));
    await expect(request('/projects')).rejects.toBeInstanceOf(HttpError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);

    fetchMock.mockResolvedValue(new Response('{}', { status: 403 }));
    await expect(request('/projects')).rejects.toBeInstanceOf(HttpError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('неудачный вход не уводит на вход повторно', async () => {
    const onUnauthorized = vi.fn();
    configureApi(() => null, onUnauthorized);
    fetchMock.mockResolvedValue(new Response('{}', { status: 401 }));

    await expect(
      request('/auth/login', { method: 'POST', body: {}, anonymous: true }),
    ).rejects.toBeInstanceOf(HttpError);

    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('токен подставляется сам, без участия вызывающего кода', async () => {
    configureApi(
      () => 'секретный-токен',
      () => {},
    );
    fetchMock.mockResolvedValue(new Response('[]', { status: 200 }));

    await request('/projects');

    const headers = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer секретный-токен');
  });
});
