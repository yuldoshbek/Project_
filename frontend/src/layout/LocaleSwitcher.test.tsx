import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import type { Locale } from '../shared/config';
import i18n from '../shared/i18n';
import { LocaleSwitcher } from './LocaleSwitcher';

/**
 * Смена языка вне обработчика события — это внешнее обновление состояния React,
 * поэтому оборачивается в act. Иначе тест зелёный, но заливает вывод предупреждениями,
 * среди которых перестают быть видны настоящие.
 */
async function switchTo(locale: Locale): Promise<void> {
  await act(async () => {
    await i18n.changeLanguage(locale);
  });
}

afterEach(async () => {
  await switchTo('ru');
});

describe('переключатель языка', () => {
  it('меняет язык интерфейса без перезагрузки страницы', async () => {
    const user = userEvent.setup();
    render(<LocaleSwitcher />);

    const select = screen.getByRole('combobox');
    expect(screen.getByText('Язык интерфейса')).toBeInTheDocument();

    await user.selectOptions(select, 'uz-Latn');

    expect(i18n.language).toBe('uz-Latn');
    expect(screen.getByText('Interfeys tili')).toBeInTheDocument();

    await user.selectOptions(select, 'uz-Cyrl');
    expect(screen.getByText('Интерфейс тили')).toBeInTheDocument();
  });

  it('названия языков не переводятся: пользователь ищет свой язык на своём языке', async () => {
    render(<LocaleSwitcher />);

    for (const name of ['Русский', 'Ўзбекча', 'Oʻzbekcha']) {
      expect(screen.getByRole('option', { name })).toBeInTheDocument();
    }

    await switchTo('uz-Latn');

    for (const name of ['Русский', 'Ўзбекча', 'Oʻzbekcha']) {
      expect(screen.getByRole('option', { name })).toBeInTheDocument();
    }
  });

  it('проставляет атрибут lang, чтобы браузер знал письменность', async () => {
    render(<LocaleSwitcher />);

    await switchTo('uz-Cyrl');
    expect(document.documentElement.lang).toBe('uz-Cyrl');

    await switchTo('uz-Latn');
    expect(document.documentElement.lang).toBe('uz-Latn');
  });
});
