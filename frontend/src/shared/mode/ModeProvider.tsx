/**
 * Хранит выбранный режим и сообщает его каждому запросу.
 *
 * Провайдер, а не глобальная переменная: режим меняется в шапке, а читают его и экраны,
 * и клиент API. Через контекст перерисовка происходит сама; с переменной пришлось бы
 * помнить, кого обновить после переключения, и однажды забыть.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { configureApi } from '../api/client';
import { DEFAULT_MODE, isMode, MODE_STORAGE_KEY, ModeContext, type Mode } from './ModeContext';

function readStoredMode(): Mode {
  // Хранилище недоступно в приватном окне и при запрете на данные сайта, а чтение там
  // бросает исключение, а не возвращает null. Падать из-за настройки браузера нельзя.
  try {
    const saved = window.localStorage.getItem(MODE_STORAGE_KEY);
    return isMode(saved) ? saved : DEFAULT_MODE;
  } catch {
    return DEFAULT_MODE;
  }
}

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(readStoredMode);

  // Клиент API читает режим через эту функцию при каждом запросе, а не получает его
  // значением: иначе после переключения в полёте остались бы запросы со старой подписью.
  useEffect(() => {
    configureApi(() => mode);
  }, [mode]);

  const setMode = useCallback((next: Mode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(MODE_STORAGE_KEY, next);
    } catch {
      // Выбор не сохранился — работать это не мешает, переживёт только до перезагрузки.
    }
  }, []);

  const value = useMemo(() => ({ mode, setMode }), [mode, setMode]);

  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
}
