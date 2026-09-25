/**
 * Доступ к теме из компонентов.
 *
 * Отдельным файлом от `ThemeProvider` не ради чистоты: модуль, который экспортирует и
 * компонент, и хук, ломает быстрое обновление в разработке — правка темы перезагружает
 * страницу целиком, и несохранённое состояние экрана теряется.
 */

import { useContext } from 'react';

import { ThemeContext, type ThemeValue } from './themeContext';

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme вне ThemeProvider');
  return value;
}
