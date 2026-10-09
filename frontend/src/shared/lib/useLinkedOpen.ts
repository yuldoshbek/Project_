/**
 * Карточка раздела, открытая ссылкой `?open=<id>`: так её открывают Календарь и поиск.
 *
 * Ссылка может прийти, когда раздел уже на экране: поиск открыт поверх раздела, и переход
 * к находке не перемонтирует его. Поэтому смена ссылки открывает карточку сразу — по
 * образцу «состояние из пропса» React, без эффекта. Закрытие убирает `open` из адреса:
 * иначе повторный поиск той же записи не сменил бы ссылку, и карточка не открылась бы.
 */

import { useNavigate, useSearch } from '@tanstack/react-router';
import { useCallback, useState } from 'react';

export function useLinkedOpen(): readonly [string | null, (id: string | null) => void] {
  const search: { open?: unknown } = useSearch({ strict: false });
  const navigate = useNavigate();
  const linked = typeof search.open === 'string' ? search.open : null;
  const [open, setOpenState] = useState(linked);
  const [seen, setSeen] = useState(linked);
  if (linked !== seen) {
    setSeen(linked);
    setOpenState(linked);
  }

  const setOpen = useCallback(
    (id: string | null) => {
      setOpenState(id);
      if (id === null && linked !== null) {
        void navigate({
          to: '.',
          search: (previous: Record<string, unknown>) =>
            Object.fromEntries(Object.entries(previous).filter(([key]) => key !== 'open')),
          replace: true,
        });
      }
    },
    [linked, navigate],
  );

  return [open, setOpen] as const;
}
