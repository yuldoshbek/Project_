import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Контраст — критерий приёмки, а не осмотр макета (ORB-088, ADR-0021).
 *
 * Тест читает сам `tokens.css`, а не копию значений: копия разойдётся с источником на первой
 * правке палитры, и тогда зелёный тест будет означать, что кто-то когда-то проверил
 * другие цвета. Порог здесь — единственное место, где записано, что «читаемо» это
 * число, а не мнение.
 *
 * Пороги WCAG 2.1: 4.5:1 для текста, 3:1 для знака, несущего смысл без подписи.
 */

/**
 * Файл читается с диска, а не через импорт CSS: в vitest обработка стилей отключена, и
 * `import './tokens.css?raw'` вернул бы заглушку — тест был бы зелёным, ничего не
 * проверив. Путь берётся от корня пакета, потому что тесты запускаются из `frontend`.
 */
const TOKENS = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8');

/** Значения из блока `:root` — тёмная тема, основная. */
const DARK = parseBlock(/:root\s*\{([\s\S]*?)\n\}/);
/** Значения из блока `[data-theme='light']` — светлая тема. */
const LIGHT = { ...DARK, ...parseBlock(/:root\[data-theme='light'\]\s*\{([\s\S]*?)\n\}/) };

/**
 * Достаёт токен по имени и падает, если его нет. Индексный доступ в строгом режиме даёт
 * `string | undefined`, и молчаливое `undefined` здесь опаснее падения: контраст
 * посчитался бы от `NaN`, а тест остался бы зелёным.
 */
function token(palette: Record<string, string>, name: string): string {
  const value = palette[name];
  if (value === undefined) throw new Error(`Токен не найден: ${name}`);
  return value;
}

function parseBlock(pattern: RegExp): Record<string, string> {
  const body = TOKENS.match(pattern)?.[1];
  if (body === undefined) throw new Error(`Блок токенов не найден: ${String(pattern)}`);

  const values: Record<string, string> = {};
  for (const match of body.matchAll(/(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})\s*;/g)) {
    const [, name, value] = match;
    if (name === undefined || value === undefined) continue;
    values[name] = value;
  }
  return values;
}

function channel(value: number): number {
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const digits = hex.replace('#', '');
  const full =
    digits.length === 3
      ? digits
          .split('')
          .map((d) => d + d)
          .join('')
      : digits;
  const [r, g, b] = [0, 2, 4].map((i) => channel(Number.parseInt(full.slice(i, i + 2), 16) / 255));
  return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (b ?? 0);
}

function contrast(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** Токены, которыми набирают текст: подписи, ссылки, числа. Порог 4.5:1. */
const AS_TEXT = ['--color-text', '--color-text-muted', '--color-accent', '--color-accent-hover'];

/**
 * Токены состояния. В тёмной теме все берут порог текста, в светлой шесть не берут и
 * годятся только как знак с подписью — принцип «цвет никогда не один» из дизайн-системы.
 * Это давний долг светлой палитры, названный в ADR-0021, а не следствие тёмной.
 */
const AS_SIGN = [
  '--color-health-green',
  '--color-health-yellow',
  '--color-health-red',
  '--color-health-grey',
  '--color-status-initiation',
  '--color-status-in-progress',
  '--color-status-on-hold',
  '--color-status-awaiting-decision',
  '--color-status-done',
  '--color-status-cancelled',
  '--color-priority-urgent',
  '--color-priority-high',
  '--color-priority-normal',
  '--color-priority-low',
];

/**
 * Четыре различных значения под шестью именами: цвета статусов переиспользуют значения
 * светофора (`status-done` = `health-green` = `#1f8a4c`, `status-on-hold` =
 * `health-yellow` = `#b8770a`). Список закреплён множеством, а не счётчиком: новый
 * провалившийся токен обязан сломать тест, а не увеличить число на единицу незамеченным.
 */
const SIGN_ONLY_IN_LIGHT = new Set([
  '--color-health-green',
  '--color-health-yellow',
  '--color-status-done',
  '--color-status-on-hold',
  '--color-status-cancelled',
  '--color-priority-high',
]);

const THEMES = [
  { name: 'тёмная', palette: DARK },
  { name: 'светлая', palette: LIGHT },
] as const;

describe('контраст палитры', () => {
  it('оба блока токенов разобраны и содержат полный набор цветов', () => {
    for (const { name, palette } of THEMES) {
      expect(palette['--color-surface'], `${name}: нет поверхности`).toBeDefined();
      expect(palette['--color-bg'], `${name}: нет фона`).toBeDefined();
      for (const item of [...AS_TEXT, ...AS_SIGN]) {
        expect(palette[item], `${name}: нет токена ${item}`).toBeDefined();
      }
    }
  });

  describe.each(THEMES)('$name тема', ({ palette }) => {
    it.each(AS_TEXT)('%s набирается текстом: не ниже 4.5:1 на карточке и на фоне', (name) => {
      for (const surface of ['--color-surface', '--color-bg'] as const) {
        const ratio = contrast(token(palette, name), token(palette, surface));
        expect(
          Number(ratio.toFixed(2)),
          `${name} на ${surface}: ${ratio.toFixed(2)}:1`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    });

    it.each(AS_SIGN)('%s несёт смысл: не ниже 3:1 на карточке', (name) => {
      const ratio = contrast(token(palette, name), token(palette, '--color-surface'));
      expect(Number(ratio.toFixed(2)), `${name}: ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(3);
    });
  });

  it('в тёмной теме цвет состояния годится и как надпись: все берут 4.5:1', () => {
    const failed = AS_SIGN.filter(
      (name) => contrast(token(DARK, name), token(DARK, '--color-surface')) < 4.5,
    );
    expect(failed, 'тёмная палитра подобрана так, чтобы надпись состояния читалась').toEqual([]);
  });

  it('в светлой теме порог надписи не берут ровно известные шесть — новых не появилось', () => {
    const failed = AS_SIGN.filter(
      (name) => contrast(token(LIGHT, name), token(LIGHT, '--color-surface')) < 4.5,
    );
    expect(new Set(failed)).toEqual(SIGN_ONLY_IN_LIGHT);
  });

  it('светлая палитра не унаследована от тёмной: значения действительно переопределены', () => {
    const shared = [...AS_TEXT, ...AS_SIGN, '--color-surface', '--color-bg'].filter(
      (name) => token(DARK, name) === token(LIGHT, name),
    );
    expect(shared, 'токен с одним значением в двух темах ломает одну из них').toEqual([]);
  });
});
