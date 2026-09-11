/**
 * Навигация на телефоне.
 *
 * До ORB-079 боковое меню ниже 640 px просто исчезало: на телефоне, объявленном основным
 * видом ([ADR-0019](../../../docs/adr/ADR-0019-leader-is-direct-user.md)), не было
 * никакой навигации вовсе. Это не недоделка оформления — это экран, с которого нельзя
 * никуда уйти.
 *
 * Все семь разделов на виду, ничего не спрятано за «ещё»: пунктов немного, а спрятанный
 * раздел — это раздел, которым перестают пользоваться. Когда они не помещаются, полоса
 * **прокручивается, а не обрезается** — прямое требование критерия приёмки.
 */

import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';

import { NAV_ITEMS } from '../app/routes';
import { cx } from '../shared/ui/cx';
import { SECTION_ICONS } from '../shared/ui/icons';
import styles from './layout.module.css';

export function BottomNav() {
  const { t } = useTranslation();

  return (
    <nav className={styles.bottomNav} aria-label={t('nav.mobileSections')}>
      <ul className={styles.bottomList}>
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end ?? false}
              className={({ isActive }) =>
                cx(styles.bottomLink, isActive && styles.bottomLinkActive)
              }
            >
              {SECTION_ICONS[item.labelKey]}
              <span className={styles.bottomLabel}>{t(item.labelKey)}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
