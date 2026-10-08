/**
 * Корень приложения и своя ссылка: помощник перевыпустил её в «Управлении», перевыпуск
 * погасил и эту сессию — на отказ `/api/me` встаёт экран с новой ссылкой. Когда сессия снова
 * есть, прежняя ссылка из кэша новой больше не считается: следующий отказ её не показывает.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { AccessLink, CurrentUser } from '@/shared/api/orbita';
import { currentUserQuery, issuedLinkQuery } from '@/shared/api/queries';

import { App } from './App';

// Здесь проверяется выбор экрана по сессии, а не маршруты и не раскладка оболочки.
vi.mock('@tanstack/react-router', () => ({ Outlet: () => <p>раздел</p> }));
vi.mock('@/app/shell/AppShell', () => ({
  AppShell: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));

const ASSISTANT: CurrentUser = {
  id: 'u-assistant',
  full_name: 'Помощник',
  role: 'assistant',
  locale: 'ru',
  timezone: 'Asia/Tashkent',
  can_write: true,
};

const LINK: AccessLink = {
  url: 'https://orbita.test/api/access/новая',
  issued_at: '2026-09-29T04:00:00Z',
};

let session = true;

beforeEach(() => {
  session = true;
  vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
    Promise.resolve({
      ok: session,
      status: session ? 200 : 401,
      statusText: '',
      json: () => Promise.resolve(session ? ASSISTANT : { detail: 'Нужна личная ссылка' }),
    } as unknown as Response),
  );
});

afterEach(() => vi.restoreAllMocks());

function renderApp(): QueryClient {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
  return client;
}

/** Перевыпуск своей ссылки: сессия погашена, ссылка в кэше, `/api/me` спрошен сразу. */
async function reissueOwn(client: QueryClient, link: AccessLink | null) {
  session = false;
  if (link) client.setQueryData(issuedLinkQuery('assistant').queryKey, link);
  await act(() => client.invalidateQueries({ queryKey: currentUserQuery().queryKey }));
}

describe('App', () => {
  it('своя ссылка перевыпущена: на отказ — экран с новой ссылкой', async () => {
    const client = renderApp();
    expect(await screen.findByText('раздел')).toBeInTheDocument();

    await reissueOwn(client, LINK);

    expect(
      await screen.findByRole('heading', { name: 'Ваша ссылка перевыпущена' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Открыть по новой ссылке' })).toHaveAttribute(
      'href',
      LINK.url,
    );
  });

  it('снова вошли — следующий отказ прежнюю ссылку не показывает', async () => {
    const client = renderApp();
    await screen.findByText('раздел');
    await reissueOwn(client, LINK);
    await screen.findByRole('heading', { name: 'Ваша ссылка перевыпущена' });

    session = true;
    fireEvent.click(screen.getByRole('button', { name: 'Проверить снова' }));
    expect(await screen.findByText('раздел')).toBeInTheDocument();

    await reissueOwn(client, null);
    expect(
      await screen.findByRole('heading', { name: /по своей личной ссылке/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Открыть по новой ссылке' })).not.toBeInTheDocument();
  });
});
