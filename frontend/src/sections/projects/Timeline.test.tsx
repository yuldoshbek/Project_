/**
 * Шкала таймлайна — месяцы на языке интерфейса.
 *
 * Форматтер, собранный при загрузке модуля, навсегда оставался русским: в узбекском
 * интерфейсе шкала показывала «окт», «нояб» (замечание ревью блока 3).
 */

import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { applyLocale } from '@/shared/i18n';

import { card } from './test-data';
import { Timeline } from './Timeline';

const RUSSIAN_SHORT_MONTH = /^(июль|авг|сент|окт|нояб)$/;

function months(): string[] {
  // Подписи месяцев — нижняя строка каждой ячейки шкалы над строками проектов.
  const scale = document.querySelector('.h-10');
  return [...(scale?.querySelectorAll('span.truncate') ?? [])].map(
    (each) => each.textContent ?? '',
  );
}

afterEach(async () => {
  await act(() => applyLocale('ru'));
});

describe('таймлайн', () => {
  it('подписи месяцев следуют за языком интерфейса', async () => {
    render(<Timeline items={[card({ id: 'pr-001' })]} today="2026-10-05" onOpen={() => {}} />);
    expect(months()).toEqual(['июль', 'авг', 'сент', 'окт', 'нояб']);

    await act(() => applyLocale('uz_latn'));
    expect(months()).toEqual(['Iyl', 'Avg', 'Sen', 'Okt', 'Noy']);
    expect(months().filter((label) => RUSSIAN_SHORT_MONTH.test(label))).toEqual([]);
    expect(screen.getByText('Okt')).toBeInTheDocument();
  });
});
