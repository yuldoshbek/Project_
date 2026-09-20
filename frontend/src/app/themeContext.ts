/**
 * Контекст темы: только объявление, без компонентов и без хуков.
 *
 * Разделение нужно правилу быстрого обновления — см. `useTheme.ts`.
 */

import { createContext } from 'react';

export type ThemeMode = 'light' | 'dim' | 'system';
export type ThemeName = 'light' | 'dim';

export interface ThemeValue {
  mode: ThemeMode;
  theme: ThemeName;
  setMode: (mode: ThemeMode) => void;
}

export const ThemeContext = createContext<ThemeValue | null>(null);
