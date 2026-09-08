import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';

import { NAV_ITEMS } from '../app/routes';
import { cx } from '../shared/ui/cx';
import styles from './layout.module.css';

/** Боковое меню. Состав повторяет раздел 9 ТЗ и берётся из `NAV_ITEMS`. */
export function Sidebar() {
  const { t } = useTranslation();

  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <span className={styles.brandName}>{t('app.name')}</span>
        <span className={styles.brandTagline}>{t('app.tagline')}</span>
      </div>

      <nav aria-label={t('nav.section')}>
        <ul className={styles.navList}>
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end ?? false}
                className={({ isActive }) => cx(styles.navLink, isActive && styles.navLinkActive)}
              >
                <span className={styles.navLabel}>{t(item.labelKey)}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
