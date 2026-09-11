/**
 * Контекст сессии: типы и сам контекст, отдельно от компонента.
 *
 * Разделение не стилистическое. Файл, который экспортирует и компонент, и что-то ещё,
 * ломает быстрое обновление при разработке: правка хука перезагружает всё дерево вместо
 * одного компонента. Правило `react-refresh/only-export-components` ловит это, и обойти
 * его подавлением значило бы оставить неудобство ради экономии одного файла.
 */

import { createContext } from 'react';

export interface Profile {
  id: string;
  email: string;
  full_name: string;
  role: 'assistant' | 'leader';
  locale: string;
  timezone: string;
  must_change_password: boolean;
}

export type SessionStatus = 'restoring' | 'anonymous' | 'signed-in';

export interface SessionValue {
  status: SessionStatus;
  profile: Profile | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const SessionContext = createContext<SessionValue | null>(null);
