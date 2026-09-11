/**
 * Состояние входа на всё приложение.
 *
 * Восстановление сессии при запуске: если токен обновления пережил перезагрузку, он
 * меняется на новый токен доступа. Пока обмен идёт, приложение не решает, вошёл
 * пользователь или нет, — иначе при каждой перезагрузке мелькал бы экран входа у того,
 * кто уже вошёл.
 */

import type { ReactNode } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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

  // Клиент API узнаёт, откуда брать токен и что делать при 401 до первого запроса.
  // Не в эффекте: эффекты выполняются после отрисовки, а запрос уходит уже из неё.
  configureApi(getAccessToken, drop);

  const adopt = useCallback(async (tokens: Tokens) => {
    rememberTokens(tokens);
    const me = await request<Profile>('/me');
    setProfile(me);
    setStatus('signed-in');
  }, []);

  const restored = useRef(false);

  useEffect(() => {
    // Восстановление ровно одно на монтирование.
    //
    // Это не оптимизация. Токен обновления **одноразовый**, и повторное предъявление
    // сервер считает кражей: он отзывает все сессии пользователя (ORB-006, и это
    // правильное поведение). В режиме разработки React вызывает эффекты дважды — и
    // второй вызов уносил сессию сразу после входа. Найдено не рассуждением, а тем,
    // что приложение само себя разлогинивало при каждой перезагрузке.
    if (restored.current) return;
    restored.current = true;

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
