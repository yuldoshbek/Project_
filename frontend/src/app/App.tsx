/**
 * Корень приложения: сессия, оболочка, содержимое раздела.
 *
 * Порядок проверок важен. Сначала выясняется, есть ли сессия: без неё показывать оболочку
 * с пустыми разделами — значит обещать данные, которых человек не увидит. Ошибка сети — не
 * то же самое, что отсутствие сессии, и разводятся они по коду ответа, а не по тексту.
 */

import { useQueryClient } from '@tanstack/react-query';
import { Outlet } from '@tanstack/react-router';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { NeedsLink } from '@/app/NeedsLink';
import { useCurrentUser } from '@/app/session';
import { AppShell } from '@/app/shell/AppShell';
import { ApiError, describeError } from '@/shared/api/client';
import { issuedLinkQuery } from '@/shared/api/queries';
import { applyLocale } from '@/shared/i18n';
import { Failure, Loading } from '@/shared/ui/States';

export function App() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const client = useQueryClient();
  const role = user.data?.role;

  // Сессия снова есть — своя ссылка, выпущенная до неё, больше не новая: следующий отказ
  // (истечение, перевыпуск с другого устройства) не должен показывать её действующей.
  // Отказ `dataUpdatedAt` не меняет, поэтому ссылка переживает тот отказ, ради которого лежит.
  useEffect(() => {
    if (role) client.removeQueries({ queryKey: issuedLinkQuery(role).queryKey, exact: true });
  }, [client, role, user.dataUpdatedAt]);

  // Язык — у пользователя на сервере: тот же на любом устройстве, где открыта ORBITA.
  const locale = user.data?.locale;
  useEffect(() => {
    if (locale) void applyLocale(locale);
  }, [locale]);

  if (user.isPending) {
    return (
      <div className="grid min-h-dvh place-items-center bg-app">
        <Loading label={t('common.loading')} />
      </div>
    );
  }

  if (user.error instanceof ApiError && user.error.needsLink) {
    // Помощник перевыпустил свою ссылку и погасил эту сессию: показать новую ссылку теперь
    // может только этот экран. Прежний ответ `/api/me` остаётся при отказе — по нему и роль.
    const fresh = user.data
      ? client.getQueryData(issuedLinkQuery(user.data.role).queryKey)
      : undefined;
    return <NeedsLink fresh={fresh} onRetry={() => void user.refetch()} />;
  }

  if (user.isError) {
    return (
      <div className="grid min-h-dvh place-items-center bg-app px-6">
        <div className="w-full max-w-md">
          <Failure detail={describeError(user.error)} onRetry={() => void user.refetch()} />
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
