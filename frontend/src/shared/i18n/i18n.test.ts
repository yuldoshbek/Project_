/**
 * Словари — полнота и подстановки (критерий 3 блока 3: интерфейс полностью переключается).
 *
 * Пропущенный узбекский ключ не упал бы: i18next молча показал бы русскую строку. Поэтому
 * полнота проверяется здесь, ключ за ключом; из множественных форм русского (`_one`,
 * `_few`, `_many`, `_other`) узбекскому нужны `_one` и `_other`. Подстановки `{{…}}` —
 * те же, что в русском: потерянная подстановка — это пустое место вместо числа.
 *
 * Полнота словарей не видит слов, которые собирает не словарь: месяцы дают `Intl`, названия
 * статусов — справочник. Так узбекский интерфейс жил с русскими месяцами в Ижро, Программах
 * и на таймлайне при зелёных проверках, поэтому эти слова проверяются отдельно.
 */

import i18next from 'i18next';
import { afterEach, describe, expect, it } from 'vitest';

import { dayOfYear, monthTitle as calendarMonth } from '@/sections/calendar/text';
import { dueLabel } from '@/sections/ijro/text';
import { monthTitle as programMonth } from '@/sections/programs/text';

import { applyLocale, localName } from '.';
import { ru } from './ru';
import { uzCyrl } from './uz-cyrl';
import { uzLatn } from './uz-latn';

const PLURAL = /_(zero|one|two|few|many|other)$/;

function flatten(tree: object, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'object' && value !== null) {
      for (const [inner, text] of flatten(value as object, path)) out.set(inner, text);
    } else {
      out.set(path, String(value));
    }
  }
  return out;
}

function expected(): Map<string, string> {
  const keys = new Map<string, string>();
  for (const [key, text] of flatten(ru)) {
    const plural = PLURAL.exec(key);
    if (!plural) keys.set(key, text);
    else {
      const base = key.slice(0, plural.index);
      keys.set(`${base}_one`, text);
      keys.set(`${base}_other`, text);
    }
  }
  return keys;
}

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((match) => match[1]!).sort();
}

afterEach(async () => {
  await applyLocale('ru');
});

describe.each([
  ['латиница', uzLatn],
  ['кириллица', uzCyrl],
])('узбекский словарь: %s', (_, dictionary) => {
  const want = expected();
  const have = flatten(dictionary);

  it('есть каждый ключ русского и нет лишних', () => {
    expect([...want.keys()].filter((key) => !have.has(key))).toEqual([]);
    expect([...have.keys()].filter((key) => !want.has(key))).toEqual([]);
  });

  it('подстановки те же, что в русском, и строки не пустые', () => {
    const broken = [...want].filter(([key, text]) => {
      const translated = have.get(key) ?? '';
      return !translated.trim() || placeholders(translated).join() !== placeholders(text).join();
    });
    expect(broken.map(([key]) => key)).toEqual([]);
  });
});

describe('переключение языка', () => {
  it('узбекский подгружается и переключает интерфейс, число — по правилам языка', async () => {
    await applyLocale('uz_latn');
    expect(i18next.t('sections.ideas')).toBe('Gʻoyalar va xaritalar');
    expect(i18next.t('ideas.awaiting.main', { count: 5 })).toBe(
      '5 ta gʻoya sizning «ha»ingizni kutmoqda',
    );
    expect(document.documentElement.lang).toBe('uz-Latn');

    await applyLocale('uz_cyrl');
    expect(i18next.t('sections.ideas')).toBe('Ғоялар ва хариталар');

    await applyLocale('ru');
    expect(i18next.t('ideas.awaiting.main', { count: 5 })).toBe('5 идей ждут вашего «да»');
  });

  it('неизвестный язык — русский', async () => {
    await applyLocale('en');
    expect(i18next.language).toBe('ru');
  });

  it('пока грузится словарь, выбрали другой язык — побеждает последний выбор', async () => {
    i18next.removeResourceBundle('uz-Latn', 'translation');
    const slow = applyLocale('uz_latn');
    const last = applyLocale('ru');

    expect(await last).toBe(true);
    expect(await slow).toBe(false);
    expect(i18next.language).toBe('ru');
    expect(document.documentElement.lang).toBe('ru');
    // Догруженный словарь не выбрасывается: следующий выбор не идёт за ним в сеть.
    expect(i18next.hasResourceBundle('uz-Latn', 'translation')).toBe(true);
  });

  it('два словаря грузятся одновременно — язык того, что выбран последним', async () => {
    i18next.removeResourceBundle('uz-Latn', 'translation');
    i18next.removeResourceBundle('uz-Cyrl', 'translation');
    const first = applyLocale('uz_cyrl');
    const last = applyLocale('uz_latn');

    await Promise.all([first, last]);
    expect(i18next.language).toBe('uz-Latn');
  });
});

describe('слова из Intl и справочников — на языке интерфейса', () => {
  const t = i18next.t.bind(i18next);
  const RUSSIAN_MONTH =
    /январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр/i;

  it('месяц в сроке Ижро, в «до конца года» Программ и в календаре — не русский', async () => {
    await applyLocale('uz_latn');
    expect(dueLabel(t, { due_on: '2026-10-15', due_precision: 'month' })).toBe('2026-yil oktabr');
    expect(programMonth('2026-10-01')).toBe('Oktabr');
    expect(calendarMonth('2026-10')).toBe('Oktabr 2026');
    expect(dayOfYear(1, 20)).not.toMatch(RUSSIAN_MONTH);

    await applyLocale('uz_cyrl');
    expect(dueLabel(t, { due_on: '2026-10-15', due_precision: 'month' })).toBe('2026-йил октябр');
    expect(programMonth('2026-11-01')).toBe('Ноябр');

    await applyLocale('ru');
    expect(dueLabel(t, { due_on: '2026-10-15', due_precision: 'month' })).toBe('октябрь 2026');
    expect(programMonth('2026-10-01')).toBe('Октябрь');
  });

  it('несуществующий день правила цикла: число на месте дня, без склейки «30 1-fevral»', async () => {
    await applyLocale('uz_latn');
    expect(dayOfYear(2, 30)).toBe('30-fevral');
    expect(dayOfYear(2, 29)).toBe('29-fevral');

    await applyLocale('uz_cyrl');
    expect(dayOfYear(2, 30)).toBe('30 феврал');

    await applyLocale('ru');
    expect(dayOfYear(2, 30)).toBe('30 февраля');
  });

  it('название из справочника — на текущем языке, пустое — русское', async () => {
    const names = { ru: 'В работе', uz_latn: 'Ishda', uz_cyrl: 'Ишда' };
    expect(localName(names)).toBe('В работе');

    await applyLocale('uz_latn');
    expect(localName(names)).toBe('Ishda');
    expect(localName({ ...names, uz_latn: '' })).toBe('В работе');
    expect(localName(names, 'uz-Cyrl')).toBe('Ишда');
  });
});
