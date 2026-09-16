import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  apply,
  isThemeMode,
  readMode,
  resolve,
  THEME_MODES,
  watchSystem,
  writeMode,
  type ThemeMode,
} from '../shared/theme/theme';
import styles from './layout.module.css';

/**
 * Переключатель темы оформления.
 *
 * Три состояния, а не два ([ADR-0021](../../../docs/adr/ADR-0021-cosmic-visual-layer.md)):
 * система, светлая, тёмная. «Система» — полноценный выбор, а не его отсутствие: телефон
 * руководителя переключается на тёмное по расписанию сам, и тумблер без этого состояния
 * заставил бы его переключать тему руками дважды в сутки.
 *
 * Первичную тему ставит встроенный скрипт в `index.html` до первой отрисовки. Здесь она
 * только меняется по выбору и следует за системой, пока выбрана «система».
 */
export function ThemeSwitcher() {
  const { t } = useTranslation();
  const selectId = useId();
  const [mode, setMode] = useState<ThemeMode>(() => readMode());

  useEffect(() => {
    apply(resolve(mode));
    if (mode !== 'system') return;
    return watchSystem(apply);
  }, [mode]);

  return (
    <div className={styles.localeSwitcher}>
      <label htmlFor={selectId} className={styles.localeLabel}>
        {t('theme.label')}
      </label>
      <select
        id={selectId}
        className={styles.localeSelect}
        value={mode}
        onChange={(event) => {
          const next = event.target.value;
          if (!isThemeMode(next)) return;
          writeMode(next);
          setMode(next);
        }}
      >
        {THEME_MODES.map((value) => (
          <option key={value} value={value}>
            {t(`theme.${value}`)}
          </option>
        ))}
      </select>
    </div>
  );
}
