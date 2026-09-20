/**
 * Корень приложения: сессия, оболочка, содержимое раздела.
 *
 * Порядок проверок важен. Сначала выясняется, есть ли сессия: без неё показывать оболочку
 * с пустыми разделами — значит обещать данные, которых человек не увидит. Ошибка сети — не
 * то же самое, что отсутствие сессии, и разводятся они по коду ответа, а не по тексту.
 */

import { Outlet } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { NeedsLink } from '@/app/NeedsLink';
import { useCurrentUser } from '@/app/session';
import { AppShell } from '@/app/shell/AppShell';
import { ApiError } from '@/shared/api/client';
import { Failure, Loading } from '@/shared/ui/States';

export function App() {
  const { t } = useTranslation();
  const user = useCurrentUser();

  if (user.isPending) {
    return (
      <div className="grid min-h-dvh place-items-center bg-app">
        <Loading label={t('common.loading')} />
      </div>
    );
  }

  if (user.error instanceof ApiError && user.error.needsLink) {
    return <NeedsLink onRetry={() => void user.refetch()} />;
  }

  if (user.isError) {
    return (
      <div className="grid min-h-dvh place-items-center bg-app px-6">
        <div className="w-full max-w-md">
          <Failure
            detail={user.error instanceof ApiError ? user.error.detail : String(user.error)}
            onRetry={() => void user.refetch()}
          />
        </div>
      </div>
    );
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
