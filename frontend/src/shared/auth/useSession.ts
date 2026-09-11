/** Доступ к сессии из компонентов. */

import { useContext } from 'react';

import type { SessionValue } from './SessionContext';
import { SessionContext } from './SessionContext';

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error('useSession вне AuthProvider');
  return value;
}
