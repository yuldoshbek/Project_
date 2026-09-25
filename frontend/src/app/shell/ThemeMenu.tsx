/**
 * Выбор темы: светлая, приглушённая, как в системе.
 *
 * Не круговой переключатель, и это решение из практики. При круговом порядке первое
 * нажатие из состояния «как в системе» на светлом экране ничего не меняет: режим стал
 * «светлая», картинка прежняя — и человек нажимает ещё раз, думая, что кнопка сломана.
 * Проверка это поймала, и переключатель стал явным выбором из трёх.
 *
 * Меню закрывается по нажатию снаружи и по Esc: на телефоне промах мимо меню — обычное
 * дело, и оно не должно оставаться висеть.
 */

import { Check, Moon, Sun, SunMoon } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ThemeMode } from '@/app/themeContext';
import { useTheme } from '@/app/useTheme';
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
        </div>
      ) : null}
    </div>
  );
}
