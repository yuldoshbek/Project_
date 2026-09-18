import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { isMode, MODES } from '../shared/mode/ModeContext';
import { useMode } from '../shared/mode/useMode';
import styles from './layout.module.css';

/**
 * Переключатель режима работы: помощник или руководитель.
 *
 * Занял место, где раньше стояли имя вошедшего и кнопка «Выйти». Входа в системе нет
 * ([ADR-0026](../../../docs/adr/ADR-0026-no-login-perimeter-auth.md)), выходить неоткуда,
 * и вопрос «кто ты» превратился из пропуска в подпись: выбранный режим уходит с каждым
 * запросом и ложится в журнал изменений автором.
 *
 * Переключатель, а не автоматическое определение: два человека работают за одним
 * ноутбуком, когда разбирают портфель вместе, и угадать, кто сейчас держит мышь,
 * неоткуда.
 */
export function ModeSwitcher() {
  const { t } = useTranslation();
  const selectId = useId();
  const { mode, setMode } = useMode();

  return (
    <div className={styles.localeSwitcher}>
      <label htmlFor={selectId} className={styles.localeLabel}>
        {t('mode.label')}
      </label>
      <select
        id={selectId}
        className={styles.localeSelect}
        value={mode}
        onChange={(event) => {
          const next = event.target.value;
          if (!isMode(next)) return;
          setMode(next);
        }}
      >
        {MODES.map((value) => (
          <option key={value} value={value}>
            {t(`mode.${value}`)}
          </option>
        ))}
      </select>
    </div>
  );
}
