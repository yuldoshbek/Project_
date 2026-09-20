/**
 * Тема: светлая, приглушённая или «как в системе».
 *
 * Значение живёт в атрибуте `data-theme` на `<html>`, а не в состоянии React: тему ставит
 * встроенный скрипт в index.html до первой отрисовки, иначе на приглушённой теме видна
 * светлая вспышка. Здесь — только переключатель и запоминание выбора.
 *
 * Состояние «как в системе» не снимает атрибут, а подставляет вычисленное значение. Иначе
 * приглушённую палитру пришлось бы описывать дважды — под медиа-запрос и под атрибут, — а
 * два списка из сорока цветов расходятся на первой же правке.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { ThemeContext, type ThemeMode, type ThemeName, type ThemeValue } from './themeContext';

const STORAGE_KEY = 'orbita.theme';

function systemTheme(): ThemeName {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dim' : 'light';
}

function readMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === 'light' || saved === 'dim' ? saved : 'system';
  } catch {
    // Хранилище недоступно: приватное окно, запрет на данные сайта. Это рабочее
    // состояние, а не отказ — тема просто не запомнится между открытиями.
    return 'system';
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readMode);
  const [theme, setTheme] = useState<ThemeName>(() =>
    mode === 'system' ? systemTheme() : (mode as ThemeName),
  );

  useEffect(() => {
    const resolved = mode === 'system' ? systemTheme() : (mode as ThemeName);
    setTheme(resolved);
    document.documentElement.setAttribute('data-theme', resolved);
  }, [mode]);

  useEffect(() => {
    if (mode !== 'system') return;
    // Системная тема меняется и при работающем приложении: вечером, по расписанию
    // телефона. Без подписки экран остался бы светлым до перезагрузки.
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const follow = () => {
      const resolved = systemTheme();
      setTheme(resolved);
      document.documentElement.setAttribute('data-theme', resolved);
    };
    media.addEventListener('change', follow);
    return () => media.removeEventListener('change', follow);
  }, [mode]);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    try {
      if (next === 'system') localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Выбор не запомнится — на работу это не влияет.
    }
  }, []);

  const value = useMemo<ThemeValue>(() => ({ mode, theme, setMode }), [mode, theme, setMode]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
