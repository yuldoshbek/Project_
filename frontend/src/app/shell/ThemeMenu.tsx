/**
 * Выбор темы — светлая, приглушённая, как в системе — и языка интерфейса.
 *
 * Не круговой переключатель, и это решение из практики. При круговом порядке первое
 * нажатие из состояния «как в системе» на светлом экране ничего не меняет: режим стал
 * «светлая», картинка прежняя — и человек нажимает ещё раз, думая, что кнопка сломана.
 * Проверка это поймала, и переключатель стал явным выбором из трёх.
 *
 * Меню закрывается по нажатию снаружи и по Esc: на телефоне промах мимо меню — обычное
 * дело, и оно не должно оставаться висеть.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, Moon, Sun, SunMoon } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ThemeMode } from '@/app/themeContext';
import { useTheme } from '@/app/useTheme';
import { describeError, request } from '@/shared/api/client';
import { currentUserQuery } from '@/shared/api/queries';
import {
  applyLocale,
  currentServerLocale,
  DEFAULT_LOCALE,
  LOCALE_MUTATION_KEY,
  LOCALES,
  type ServerLocale,
} from '@/shared/i18n';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';

const MODES: readonly ThemeMode[] = ['light', 'dim', 'system'];

const ICON = {
  light: Sun,
  dim: Moon,
  system: SunMoon,
} as const;

export function ThemeMenu() {
  const { t } = useTranslation();
  const { mode, setMode } = useTheme();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const Icon = ICON[mode];
  const client = useQueryClient();
  const [failure, setFailure] = useState<string | null>(null);
  // Язык включается сразу, а сохраняется на сервере вдогонку: экран не ждёт ответа.
  const language = useMutation({
    // Выборы идут по очереди. Два сохранения в полёте могли бы лечь на сервер не в том
    // порядке, в каком нажаты, а откат первого неудачного — затереть уже включённый второй.
    scope: { id: 'locale' },
    mutationKey: LOCALE_MUTATION_KEY,
    mutationFn: async (locale: ServerLocale) => {
      // Пока грузился словарь, выбрали другой язык: сохранит его собственный выбор.
      if (!(await applyLocale(locale))) return false;
      await request<void>('/api/me/locale', { method: 'PUT', body: { locale } });
      return true;
    },
    onMutate: () => setFailure(null),
    // Названия из справочников сервер отдаёт на языке пользователя (типы в проектах,
    // задачах, идеях): экран, собранный до смены, остался бы наполовину на прежнем языке.
    // Перечитывается всё — перечень таких запросов разошёлся бы с сервером при первом
    // новом справочнике.
    // Перечитывание не ждём: следующий выбор языка не должен стоять в очереди за ним.
    // Сохранённый язык сразу кладётся в `/api/me`: пока он перечитывается, в кеше не должен
    // оставаться прежний — по нему корень приложения вернул бы прежний язык на миг.
    onSuccess: (saved, locale) => {
      if (saved) {
        client.setQueryData(currentUserQuery().queryKey, (me) => (me ? { ...me, locale } : me));
      }
      void client.invalidateQueries();
    },
    // Не сохранился выбор — интерфейс возвращается к языку, записанному у пользователя:
    // иначе экран на одном языке, а после перезагрузки и на другом устройстве — на другом.
    // `/api/me` перечитывается: если сохранение всё же дошло, а потерялся ответ, язык
    // придёт оттуда.
    onError: async (error) => {
      setFailure(describeError(error));
      const saved = client.getQueryData(currentUserQuery().queryKey)?.locale;
      // Не удался и откат — экран остаётся как есть: сообщение уже на экране.
      await applyLocale(saved ?? DEFAULT_LOCALE).catch(() => false);
      void client.invalidateQueries({ queryKey: currentUserQuery().queryKey });
    },
  });
  const chosen = currentServerLocale();

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  return (
    <div className="relative" ref={box}>
      <Button
        look="quiet"
        size="icon"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${t('theme.label')}: ${t(`theme.${mode}`)}`}
        title={`${t('theme.label')}: ${t(`theme.${mode}`)}`}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon className="size-5" />
      </Button>

      {/* Меню закрывается сразу после выбора, поэтому отказ показывается под кнопкой, а не в нём */}
      {failure && !open ? (
        <div
          role="alert"
          className={cn(
            'absolute right-0 top-[calc(100%+6px)] z-50 w-64 p-3 text-sm',
            'rounded-[var(--radius)] border border-line bg-burn-soft text-burn-ink shadow-raised',
          )}
        >
          <p>{t('language.failed', { detail: failure })}</p>
          <Button className="mt-2" size="small" onClick={() => setFailure(null)}>
            {t('language.dismiss')}
          </Button>
        </div>
      ) : null}

      {open ? (
        <div
          role="menu"
          className={cn(
            'absolute right-0 top-[calc(100%+6px)] z-50 w-52 overflow-hidden',
            'rounded-[var(--radius)] border border-line bg-raised shadow-raised',
          )}
        >
          {MODES.map((value) => {
            const ModeIcon = ICON[value];
            return (
              <button
                key={value}
                type="button"
                role="menuitemradio"
                aria-checked={mode === value}
                className={cn(
                  'flex w-full min-h-touch items-center gap-2.5 px-3 text-left text-sm',
                  'transition-colors duration-[var(--motion-fast)] hover:bg-hover',
                  mode === value ? 'text-accent-ink' : 'text-ink',
                )}
                onClick={() => {
                  setMode(value);
                  setOpen(false);
                }}
              >
                <ModeIcon className="size-4 shrink-0" />
                <span className="flex-1">{t(`theme.${value}`)}</span>
                {mode === value ? <Check className="size-4" /> : null}
              </button>
            );
          })}
          <div role="group" aria-label={t('language.label')} className="border-t border-line py-1">
            <p className="px-3 pt-1 text-xs text-ink-muted">{t('language.label')}</p>
            {LOCALES.map((locale) => (
              <button
                key={locale.server}
                type="button"
                role="menuitemradio"
                aria-checked={chosen === locale.server}
                lang={locale.code}
                className={cn(
                  'flex w-full min-h-touch items-center gap-2.5 px-3 text-left text-sm',
                  'transition-colors duration-[var(--motion-fast)] hover:bg-hover',
                  chosen === locale.server ? 'text-accent-ink' : 'text-ink',
                )}
                onClick={() => {
                  language.mutate(locale.server);
                  setOpen(false);
                }}
              >
                <span className="flex-1">{locale.label}</span>
                {chosen === locale.server ? <Check className="size-4" /> : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
