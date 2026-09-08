import { useTranslation } from 'react-i18next';

import styles from './ui.module.css';

interface ErrorStateProps {
  /** Ключ локализации заголовка. По умолчанию — общая ошибка загрузки. */
  titleKey?: string;
  /** Ключ локализации пояснения. */
  hintKey?: string;
  /** Если передан — показывается кнопка повтора. */
  onRetry?: () => void;
}

/**
 * Единый вид ошибки.
 *
 * Пользователю показывается, что произошло и что делать дальше; технические подробности
 * остаются в логе. Сообщения приходят ключами локализации, а не готовым текстом, —
 * иначе на узбекской локали интерфейс заговорит по-русски.
 */
export function ErrorState({
  titleKey = 'state.errorTitle',
  hintKey = 'state.errorHint',
  onRetry,
}: ErrorStateProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.state} role="alert">
      <p className={styles.stateTitle}>{t(titleKey)}</p>
      <p className={styles.stateHint}>{t(hintKey)}</p>
      {onRetry ? (
        <button type="button" className={styles.action} onClick={onRetry}>
          {t('state.retry')}
        </button>
      ) : null}
    </div>
  );
}
