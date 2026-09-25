/**
 * Верхняя строка: кто вошёл, какая тема, что за контур.
 *
 * На телефоне в ней остаются название системы, роль вместо полного имени и переключатель
 * темы: место на экране 390 px стоит дороже, чем подпись рядом с названием.
 *
 * Высота строки — токен `--topbar-height`: по нему же прилипает боковая полоса.
 *
 * Пометка контура («превью») стоит здесь нарочно и только вне рабочего контура: человек,
 * работающий в превью, обязан видеть, что данные вымышленные, — иначе он однажды заведёт
 * настоящее поручение в копии, которая удалится вместе с закрытием PR.
 */

import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { useCurrentUser, useHealth } from '@/app/session';
import { ThemeMenu } from '@/app/shell/ThemeMenu';
import { Signal } from '@/shared/ui/Signal';

export function TopBar({ device }: { device: Device }) {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const health = useHealth();
  const isPhone = device === 'phone';

  return (
    <header className="sticky top-0 z-30 flex h-topbar print:hidden flex-col border-b border-line bg-card/95 backdrop-blur">
      {/* Тонкая полоса «космоса»: отделяет служебную строку от данных. */}
      <div className="h-0.5 w-full shrink-0 bg-gradient-to-r from-space-deep via-space-glow to-space-mid" />

      <div className="flex min-h-0 flex-1 items-center gap-3 px-4">
        <span className="font-semibold tracking-tight text-ink-strong">{t('app.name')}</span>

        {!isPhone ? (
          <span className="hidden text-sm text-ink-muted sm:inline">{t('app.tagline')}</span>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          {health.data && health.data.env !== 'production' ? (
            <Signal state="wait">
              {t(`management.state.envNames.${health.data.env}`, health.data.env)}
            </Signal>
          ) : null}

          {user.data ? (
            <span className="text-sm text-ink-muted">
              {isPhone ? t(`role.${user.data.role}`) : user.data.full_name}
            </span>
          ) : null}

          <ThemeMenu />
        </div>
      </div>
    </header>
  );
}
