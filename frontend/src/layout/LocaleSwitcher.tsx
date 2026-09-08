import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { isSupportedLocale, SUPPORTED_LOCALES } from '../shared/config';
import styles from './layout.module.css';

/**
 * Переключатель языка интерфейса.
 *
 * Меняет локаль без перезагрузки страницы (ТЗ 10.3): i18next оповещает подписчиков,
 * React перерисовывает дерево. Выбор сохраняется и переживает перезагрузку.
 *
 * Названия языков намеренно не переводятся: «Ўзбекча» должно называться так на любой
 * локали, иначе пользователь не найдёт свой язык в списке, написанном на чужом.
 */
export function LocaleSwitcher() {
  const { t, i18n } = useTranslation();
  const selectId = useId();

  return (
    <div className={styles.localeSwitcher}>
      <label htmlFor={selectId} className={styles.localeLabel}>
        {t('locale.label')}
      </label>
      <select
        id={selectId}
        className={styles.localeSelect}
        value={i18n.language}
        onChange={(event) => {
          const next = event.target.value;
          if (isSupportedLocale(next)) {
            void i18n.changeLanguage(next);
          }
        }}
      >
        {SUPPORTED_LOCALES.map((locale) => (
          <option key={locale} value={locale}>
            {t(`locale.${locale}`)}
          </option>
        ))}
      </select>
    </div>
  );
}
