/**
 * Опрос по метке изменений: данные перечитываются только тогда, когда метка сменилась.
 */

import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useChangeStamp } from './changes';
import { request } from './client';
import { QUERY_DEFAULTS } from './queries';

function Probe() {
  useChangeStamp(true);
  useQuery({ queryKey: ['pult'], queryFn: () => request<unknown>('/api/v1/pult') });
  useQuery({ queryKey: ['me'], queryFn: () => request<unknown>('/api/me') });
  return null;
}

function serve(stamps: string[]) {
  const asked: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const path = String(input);
    asked.push(path);
    const body = path === '/api/v1/changes' ? { stamp: stamps.shift() ?? 'last' } : {};
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
  return asked;
}

function renderProbe() {
  // Умолчания рабочего клиента: данные сами не опрашиваются и не устаревают.
  const client = new QueryClient({ defaultOptions: { queries: QUERY_DEFAULTS } });
  render(
    <QueryClientProvider client={client}>
      <Probe />
    </QueryClientProvider>,
  );
  return client;
}

const count = (asked: string[], path: string) => asked.filter((each) => each === path).length;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('метка изменений', () => {
  it('та же метка — данные не перечитываются', async () => {
    const asked = serve(['a', 'a']);
    const client = renderProbe();
    await waitFor(() => expect(count(asked, '/api/v1/pult')).toBe(1));
    await waitFor(() => expect(client.getQueryData(['changes'])).toEqual({ stamp: 'a' }));

    await act(() => client.refetchQueries({ queryKey: ['changes'] }));

    expect(count(asked, '/api/v1/changes')).toBe(2);
    expect(count(asked, '/api/v1/pult')).toBe(1);
  });

  it('новая метка — перечитываются данные разделов, но не «кто вошёл»', async () => {
    const asked = serve(['a', 'b']);
    const client = renderProbe();
    await waitFor(() => expect(count(asked, '/api/v1/pult')).toBe(1));
    // Первая метка — точка отсчёта: от неё и сравнивается следующая.
    await waitFor(() => expect(client.getQueryData(['changes'])).toEqual({ stamp: 'a' }));
    const me = count(asked, '/api/me');

    await act(() => client.refetchQueries({ queryKey: ['changes'] }));

    await waitFor(() => expect(count(asked, '/api/v1/pult')).toBe(2));
    expect(count(asked, '/api/me')).toBe(me);
  });
});
