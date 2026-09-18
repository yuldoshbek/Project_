/** Доступ к режиму работы из компонентов. */

import { useContext } from 'react';

import { ModeContext, type ModeValue } from './ModeContext';

export function useMode(): ModeValue {
  const value = useContext(ModeContext);
  if (value === null) throw new Error('useMode вне ModeProvider');
  return value;
}

/** Можно ли сейчас изменять данные. Руководитель смотрит, помощник вносит. */
export function useMayEdit(): boolean {
  return useMode().mode === 'assistant';
}
