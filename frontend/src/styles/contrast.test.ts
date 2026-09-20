/**
 * Контраст считается, а не осматривается.
 *
 * Глаз на светлом фоне ошибается уверенно: бледно-жёлтая подпись «ждёт» кажется читаемой
 * ровно до того момента, когда экран выносят на солнце. Поэтому пары «текст на поверхности»
 * проверяются счётом по WCAG 2.1: 4.5:1 для текста, 3:1 для знака, несущего смысл.
 *
 * Значения берутся из tokens.css разбором файла, а не переписываются сюда: копия разошлась
 * бы с источником на первой правке, и проверка подтверждала бы саму себя.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, 'tokens.css'), 'utf8');

function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`в tokens.css нет блока ${selector}`);
  const open = css.indexOf('{', start);
  const close = css.indexOf('}', open);
  const body = css.slice(open + 1, close);

  const values: Record<string, string> = {};
  for (const line of body.split('\n')) {
    const match = /^\s*(--[\w-]+):\s*(#[0-9a-fA-F]{6});/.exec(line);
    if (match?.[1] && match[2]) values[match[1]] = match[2];
  }
  return values;
}

const light = block(':root');
const dim = block("[data-theme='dim']");

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const r = Number.parseInt(hex.slice(1, 3), 16);
  const g = Number.parseInt(hex.slice(3, 5), 16);
  const b = Number.parseInt(hex.slice(5, 7), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function ratio(front: string, back: string): number {
  const a = luminance(front);
  const b = luminance(back);
  const [bright, dark] = a > b ? [a, b] : [b, a];
  return (bright + 0.05) / (dark + 0.05);
}

const TEXT_MINIMUM = 4.5;
const MARK_MINIMUM = 3;

// Текст на поверхностях. Третий уровень (`--ink-muted`) — это подписи вроде
// «по таблице от 15.09»: их читают, значит порог у них тот же.
const TEXT_PAIRS = [
  ['--ink-strong', '--surface-app'],
  ['--ink-strong', '--surface-card'],
  ['--ink', '--surface-app'],
  ['--ink', '--surface-card'],
  ['--ink-muted', '--surface-app'],
  ['--ink-muted', '--surface-card'],
  ['--ink-muted', '--surface-sunken'],
  ['--accent', '--surface-card'],
  ['--accent-ink', '--accent-soft'],
  ['--burn-ink', '--burn-soft'],
  ['--wait-ink', '--wait-soft'],
  ['--calm-ink', '--calm-soft'],
  ['--call-ink', '--call-soft'],
] as const;

// Знаки: точка сигнала и граница. Они несут смысл, но текстом не являются — порог 3:1.
const MARK_PAIRS = [
  ['--burn', '--surface-card'],
  ['--wait', '--surface-card'],
  ['--calm', '--surface-card'],
  ['--call', '--surface-card'],
  ['--line-strong', '--surface-card'],
] as const;

describe.each([
  ['светлая тема', light],
  ['приглушённая тема', dim],
])('%s', (_name, theme) => {
  it.each(TEXT_PAIRS)('текст %s на %s читается (4.5:1)', (front, back) => {
    const frontColor = theme[front];
    const backColor = theme[back];
    expect(frontColor, `в теме нет ${front}`).toBeDefined();
    expect(backColor, `в теме нет ${back}`).toBeDefined();
    expect(ratio(frontColor as string, backColor as string)).toBeGreaterThanOrEqual(TEXT_MINIMUM);
  });

  it.each(MARK_PAIRS)('знак %s на %s различим (3:1)', (front, back) => {
    const frontColor = theme[front];
    const backColor = theme[back];
    expect(ratio(frontColor as string, backColor as string)).toBeGreaterThanOrEqual(MARK_MINIMUM);
  });
});
