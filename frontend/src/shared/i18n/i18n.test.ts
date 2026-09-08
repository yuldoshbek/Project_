import { describe, expect, it } from 'vitest';

import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from '../config';
import { detectLocale, resources } from './index';

type Dict = Record<string, unknown>;

/** Плоский список ключей вида `nav.projects` — так расхождение видно поимённо. */
function flatKeys(value: Dict, prefix = ''): string[] {
  return Object.entries(value).flatMap(([key, nested]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof nested === 'object' && nested !== null ? flatKeys(nested as Dict, path) : [path];
  });
}

function valueAt(dict: Dict, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, part) => (acc as Dict)?.[part], dict);
}

const referenceKeys = flatKeys(resources[DEFAULT_LOCALE].translation as Dict).sort();

describe('словари локализации', () => {
  it.each(SUPPORTED_LOCALES)('в локали %s тот же набор ключей, что в русской', (locale) => {
    const keys = flatKeys(resources[locale].translation as Dict).sort();

    const missing = referenceKeys.filter((key) => !keys.includes(key));
    const extra = keys.filter((key) => !referenceKeys.includes(key));

    expect({ missing, extra }).toEqual({ missing: [], extra: [] });
  });

  it.each(SUPPORTED_LOCALES)('в локали %s нет пустых значений', (locale) => {
    const dict = resources[locale].translation as Dict;
    const empty = referenceKeys.filter((key) => {
      const value = valueAt(dict, key);
      return typeof value !== 'string' || value.trim() === '';
    });

    expect(empty).toEqual([]);
  });

  it.each(SUPPORTED_LOCALES)('в локали %s сохранены подстановки вида {{...}}', (locale) => {
    const reference = resources[DEFAULT_LOCALE].translation as Dict;
    const dict = resources[locale].translation as Dict;

    const broken = referenceKeys.filter((key) => {
      const expected = placeholders(String(valueAt(reference, key)));
      const actual = placeholders(String(valueAt(dict, key)));
      return expected.join() !== actual.join();
    });

    expect(broken).toEqual([]);
  });
});

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{\{(\w+)\}\}/g)].map((match) => match[1] ?? '').sort();
}

describe('определение языка при запуске', () => {
  const storage = (value: string | null) => ({ getItem: () => value });

  it('сохранённый выбор важнее языка браузера', () => {
    expect(detectLocale(storage('uz-Latn'), ['ru-RU'])).toBe('uz-Latn');
  });

  it('игнорирует сохранённое значение, которого нет в списке поддерживаемых', () => {
    expect(detectLocale(storage('klingon'), ['ru-RU'])).toBe('ru');
  });

  it('узбекский без указания письменности считается латиницей', () => {
    expect(detectLocale(storage(null), ['uz-UZ'])).toBe('uz-Latn');
  });

  it('узбекская кириллица распознаётся по тегу письменности', () => {
    expect(detectLocale(storage(null), ['uz-Cyrl-UZ'])).toBe('uz-Cyrl');
  });

  it('без подсказок берётся язык по умолчанию', () => {
    expect(detectLocale(storage(null), ['fr-FR'])).toBe(DEFAULT_LOCALE);
  });

  it('недоступное хранилище не роняет определение', () => {
    const throwing = {
      getItem: () => {
        throw new Error('доступ к хранилищу запрещён');
      },
    };
    expect(detectLocale(throwing, ['ru'])).toBe('ru');
  });
});
