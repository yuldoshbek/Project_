/**
 * Состояние входа на всё приложение.
 *
 * Восстановление сессии при запуске: если токен обновления пережил перезагрузку, он
 * меняется на новый токен доступа. Пока обмен идёт, приложение не решает, вошёл
 * пользователь или нет, — иначе при каждой перезагрузке мелькал бы экран входа у того,
 * кто уже вошёл.
 */

import type { ReactNode } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { configureApi, request } from '../api/client';
import type { Tokens } from './session';
import { forgetTokens, getAccessToken, getRefreshToken, rememberTokens } from './session';
import type { Profile, SessionStatus, SessionValue } from './SessionContext';
import { SessionContext } from './SessionContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>('restoring');
  const [profile, setProfile] = useState<Profile | null>(null);

  const drop = useCallback(() => {
    forgetTokens();
    setProfile(null);
    setStatus('anonymous');
  }, []);

  // Клиент API узнаёт, откуда брать токен и что делать при 401, один раз и до первого
  // запроса: иначе первый же запрос уйдёт без токена.
  useMemo(() => configureApi(getAccessToken, drop), [drop]);

  const adopt = useCallback(async (tokens: Tokens) => {
    rememberTokens(tokens);
    const me = await request<Profile>('/me');
    setProfile(me);
    setStatus('signed-in');
  }, []);

  useEffect(() => {
    const refresh = getRefreshToken();
    if (refresh === null) {
      setStatus('anonymous');
      return;
    }

    void (async () => {
      try {
        const tokens = await request<Tokens>('/auth/refresh', {
          method: 'POST',
          body: { refresh_token: refresh },
          anonymous: true,
        });
        await adopt(tokens);
      } catch {
        // Токен обновления мёртв: истёк, отозван или предъявлен повторно. Это не
        // ошибка приложения — это обычный конец сессии.
        drop();
      }
    })();
  }, [adopt, drop]);

  const value = useMemo<SessionValue>(
    () => ({
      status,
      profile,
      signIn: async (email, password) => {
        const tokens = await request<Tokens>('/auth/login', {
          method: 'POST',
          body: { email, password },
          anonymous: true,
        });
        await adopt(tokens);
      },
      signOut: async () => {
        const refresh = getRefreshToken();
        if (refresh !== null) {
          // Выход обязан закрыть сессию на сервере, а не только стереть токен здесь:
          // иначе «выйти» — надпись на кнопке, а не действие (ORB-006).
          try {
            await request('/auth/logout', {
              method: 'POST',
              body: { refresh_token: refresh },
            });
          } catch {
            /* сервер недоступен — локально выходим всё равно */
          }
        }
        drop();
      },
    }),
    [status, profile, adopt, drop],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
