/**
 * Карточка по ссылке `?open=`: открывается сразу, в том числе когда раздел уже на экране, и
 * закрытие убирает ссылку из адреса — иначе повторный поиск той же записи ничего не открыл бы.
 */

import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useLinkedOpen } from './useLinkedOpen';

const route = vi.hoisted(() => ({
  search: {} as Record<string, unknown>,
  navigate: vi.fn(() => Promise.resolve()),
}));
vi.mock('@tanstack/react-router', () => ({
  useSearch: () => route.search,
  useNavigate: () => route.navigate,
}));

function Probe() {
  const [open, setOpen] = useLinkedOpen();
  return (
    <div>
      <output>{open ?? 'закрыто'}</output>
      <button type="button" onClick={() => setOpen(null)}>
        закрыть
      </button>
      <button type="button" onClick={() => setOpen('своя')}>
        своя
      </button>
    </div>
  );
}

afterEach(() => {
  cleanup();
  route.search = {};
  route.navigate.mockClear();
});

describe('карточка по ссылке', () => {
  it('ссылка при входе открывает карточку', () => {
    route.search = { open: 'p-1' };
    render(<Probe />);
    expect(screen.getByRole('status')).toHaveTextContent('p-1');
  });

  it('новая ссылка, пока раздел на экране, открывает свою карточку', () => {
    const { rerender } = render(<Probe />);
    expect(screen.getByRole('status')).toHaveTextContent('закрыто');

    route.search = { open: 'p-2' };
    rerender(<Probe />);

    expect(screen.getByRole('status')).toHaveTextContent('p-2');
  });

  it('закрытие убирает ссылку из адреса, остальное в адресе остаётся', () => {
    route.search = { open: 'p-1', view: 'letters' };
    render(<Probe />);

    act(() => screen.getByRole('button', { name: 'закрыть' }).click());

    expect(screen.getByRole('status')).toHaveTextContent('закрыто');
    expect(route.navigate).toHaveBeenCalledTimes(1);
    const options = (route.navigate.mock.calls[0] as unknown[])[0] as {
      search: (previous: Record<string, unknown>) => Record<string, unknown>;
    };
    expect(options.search({ open: 'p-1', view: 'letters' })).toEqual({ view: 'letters' });
  });

  it('карточка, открытая касанием, адрес не трогает', () => {
    render(<Probe />);
    act(() => screen.getByRole('button', { name: 'своя' }).click());
    act(() => screen.getByRole('button', { name: 'закрыть' }).click());
    expect(route.navigate).not.toHaveBeenCalled();
  });
});
