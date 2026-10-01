/**
 * Экран «откройте по ссылке»: без свежей ссылки — одно предложение и проверка; после
 * перевыпуска своей ссылки — новая ссылка, иначе помощник остался бы вне системы.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { NeedsLink } from './NeedsLink';

describe('NeedsLink', () => {
  it('без свежей ссылки полей и ссылок нет', () => {
    render(<NeedsLink onRetry={vi.fn()} />);

    expect(screen.getByRole('heading', { name: /по своей личной ссылке/ })).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('своя ссылка перевыпущена: новая ссылка, открыть и скопировать', async () => {
    const url = 'https://orbita.test/api/access/новая';
    const writeText = vi.fn(() => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText } });
    const retry = vi.fn();
    render(<NeedsLink fresh={{ url, issued_at: '2026-09-29T04:00:00Z' }} onRetry={retry} />);

    expect(screen.getByRole('heading', { name: 'Ваша ссылка перевыпущена' })).toBeInTheDocument();
    expect(screen.getByText(/Ссылка показывается один раз/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Открыть по новой ссылке' })).toHaveAttribute(
      'href',
      url,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Скопировать' }));
    expect(await screen.findByRole('button', { name: 'Скопировано' })).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(url);
    fireEvent.click(screen.getByRole('button', { name: 'Проверить снова' }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
