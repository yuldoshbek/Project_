/**
 * Словари — полнота и подстановки (критерий 3 блока 3: интерфейс полностью переключается).
 *
 * Пропущенный узбекский ключ не упал бы: i18next молча показал бы русскую строку. Поэтому
 * полнота проверяется здесь, ключ за ключом; из множественных форм русского (`_one`,
 * `_few`, `_many`, `_other`) узбекскому нужны `_one` и `_other`. Подстановки `{{…}}` —
 * те же, что в русском: потерянная подстановка — это пустое место вместо числа.
 */

import i18next from 'i18next';
import { afterEach, describe, expect, it } from 'vitest';

import { applyLocale } from '.';
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
});
