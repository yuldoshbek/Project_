import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { NAV_ITEMS, ROUTES } from '../app/routes';
import styles from './layout.module.css';

/**
 * Хлебные крошки.
 *
 * Пока экраны плоские, цепочка короткая: раздел и его название. Вложенность появится
 * вместе с карточками проекта и задачи (ORB-018, ORB-022) — тогда сюда добавится
 * название конкретной записи, которое приходит с сервера, а не из словаря.
 */
export function Breadcrumbs() {
  const { t } = useTranslation();
  const { pathname } = useLocation();

  const current = NAV_ITEMS.find((item) =>
    item.end ? pathname === item.to : pathname.startsWith(item.to),
  );

  const isRoot = pathname === ROUTES.dashboard;

  return (
    <nav aria-label={t('nav.section')}>
      <ol className={styles.breadcrumbs}>
        <li>
          {isRoot ? (
            <span className={styles.breadcrumbCurrent}>{t('app.name')}</span>
          ) : (
            <Link to={ROUTES.dashboard}>{t('app.name')}</Link>
          )}
        </li>
        {current && !isRoot ? (
          <>
            <li aria-hidden="true" className={styles.breadcrumbSeparator}>
              {'/'}
            </li>
            <li>
              <span className={styles.breadcrumbCurrent} aria-current="page">
                {t(current.labelKey)}
              </span>
            </li>
          </>
        ) : null}
      </ol>
    </nav>
  );
}
