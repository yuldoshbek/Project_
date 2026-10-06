/**
 * Названия статусов из справочника — на языке интерфейса.
 *
 * Полнота словарей этого не видит: название приходит из справочника, а не из словаря, и
 * узбекский интерфейс показывал «В работе» при зелёных проверках (замечание ревью блока 3).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it } from 'vitest';

import { applyLocale } from '@/shared/i18n';

import type { Dictionaries, ProjectStatusEntry } from './orbita';
import { dictionariesQuery } from './queries';
import { useStatuses } from './statuses';

const IN_PROGRESS: ProjectStatusEntry = {
  id: 's-1',
  code: 'in_progress',
  name: { ru: 'В работе', uz_latn: 'Ishda', uz_cyrl: 'Ишда' },
  sort_order: 10,
  is_active: true,
  color: 'blue',
  is_terminal: false,
  requires_reason: false,
};

function wrapper(dictionaries: Partial<Dictionaries>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(dictionariesQuery().queryKey, dictionaries as Dictionaries);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

afterEach(async () => {
  await act(() => applyLocale('ru'));
});

describe('статусы из справочника', () => {
  it('название — на выбранном языке и меняется вместе с ним', async () => {
    const { result } = renderHook(() => useStatuses('project_statuses'), {
      wrapper: wrapper({ project_statuses: [IN_PROGRESS] }),
    });
    expect(result.current.name('in_progress')).toBe('В работе');

    await act(() => applyLocale('uz_latn'));
    expect(result.current.name('in_progress')).toBe('Ishda');

    await act(() => applyLocale('uz_cyrl'));
    expect(result.current.name('in_progress')).toBe('Ишда');
  });

  it('строки нет в справочнике — ключ перевода на том же языке и с тем же словом', async () => {
    const { result } = renderHook(() => useStatuses('project_statuses'), {
      wrapper: wrapper({ project_statuses: [] }),
    });
    // Слово — как в наполнении (`app.seed`): иначе, пока справочник едет, колонка
    // называлась бы одним словом, а через секунду другим.
    await act(() => applyLocale('uz_latn'));
    expect(result.current.name('on_hold')).toBe('Toʻxtatilgan');
    await act(() => applyLocale('uz_cyrl'));
    expect(result.current.name('on_hold')).toBe('Тўхтатилган');
  });
});
