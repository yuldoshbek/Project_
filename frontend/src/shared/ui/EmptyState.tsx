import { useTranslation } from 'react-i18next';

import styles from './ui.module.css';

interface EmptyStateProps {
  titleKey?: string;
  hintKey?: string;
}

/** Пустая выборка. Отличается от ошибки: данных нет, но система исправна. */
export function EmptyState({
  titleKey = 'state.empty',
  hintKey = 'state.emptyHint',
}: EmptyStateProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.state}>
      <p className={styles.stateTitle}>{t(titleKey)}</p>
      <p className={styles.stateHint}>{t(hintKey)}</p>
    </div>
  );
}
