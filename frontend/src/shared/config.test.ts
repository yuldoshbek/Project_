import { describe, expect, it } from 'vitest';

import { DEFAULT_LOCALE, isSupportedLocale, SUPPORTED_LOCALES } from './config';

describe('локали', () => {
  it('поддерживает три письменности из ТЗ 10.3', () => {
    expect(SUPPORTED_LOCALES).toEqual(['ru', 'uz-Cyrl', 'uz-Latn']);
  });

  it('локаль по умолчанию входит в поддерживаемые', () => {
    expect(isSupportedLocale(DEFAULT_LOCALE)).toBe(true);
  });

  it('отклоняет неизвестную локаль', () => {
    expect(isSupportedLocale('en')).toBe(false);
  });
});
