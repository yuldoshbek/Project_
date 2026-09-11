/**
 * Учётные записи и состояния сессии для тестов.
 *
 * Отдельно от компонента-обёртки: файл, экспортирующий и компонент, и константы, ломает
 * быстрое обновление при разработке, и линтер справедливо на это ругается.
 *
 * Роль задаётся явно всегда: отличие помощника от руководителя — половина поведения
 * системы (ADR-0011), и тест, который про роль не сказал, проверяет не то, что думает.
 */

import type { Profile, SessionValue } from '../shared/auth/SessionContext';

export const ASSISTANT: Profile = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'assistant@orbita.local',
  full_name: 'Личный помощник заместителя директора',
  role: 'assistant',
  locale: 'ru',
  timezone: 'Asia/Tashkent',
  must_change_password: false,
};

export const LEADER: Profile = {
  ...ASSISTANT,
  id: '00000000-0000-0000-0000-000000000002',
  email: 'leader@orbita.local',
  full_name: 'Заместитель директора',
  role: 'leader',
};

export function sessionOf(profile: Profile | null, status: SessionValue['status']): SessionValue {
  return {
    status,
    profile,
    signIn: async () => {},
    signOut: async () => {},
  };
}
