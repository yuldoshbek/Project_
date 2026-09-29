/**
 * Может ли это устройство показывать уведомления ORBITA (ТЗ 8).
 *
 * На iPhone уведомления работают только у ORBITA, установленной на экран «Домой»: в Safari их
 * нет вовсе, и кнопка «включить» там ничего бы не сделала. Поэтому сначала — установлена ли,
 * потом — умеет ли браузер, и только потом — разрешение. Что показать на каждом шаге, решает
 * экран «Сводка» (`sections/pult/Summary.tsx`).
 */

export type DeviceSetup =
  /** iPhone или iPad, ORBITA открыта в Safari: сначала — на экран «Домой». */
  | 'install'
  /** Браузер уведомлений не показывает. */
  | 'unsupported'
  /** Уведомления запрещены в настройках устройства: кнопкой их не вернуть. */
  | 'denied'
  /** Можно включать. */
  | 'ready';

export interface DeviceEnvironment {
  userAgent: string;
  /** Касаний больше одного: iPad с iPadOS называет себя «Macintosh». */
  touchPoints: number;
  /** Открыта со значка на экране «Домой», а не во вкладке браузера. */
  standalone: boolean;
  /** Есть уведомления, service worker и подписка на пуши. */
  pushCapable: boolean;
  permission: NotificationPermission | null;
}

export function readEnvironment(): DeviceEnvironment {
  const pushCapable =
    'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window;
  return {
    userAgent: navigator.userAgent,
    touchPoints: navigator.maxTouchPoints,
    standalone:
      window.matchMedia('(display-mode: standalone)').matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true,
    pushCapable,
    permission: pushCapable ? Notification.permission : null,
  };
}

/**
 * iPhone или iPad. Отличается не только установкой: запрет уведомлений снимается в настройках
 * iPhone, а в браузере на ноутбуке — в настройках сайта.
 */
export function isAppleMobile({ userAgent, touchPoints }: DeviceEnvironment): boolean {
  return /iPhone|iPad|iPod/.test(userAgent) || (/Macintosh/.test(userAgent) && touchPoints > 1);
}

export function deviceSetup(environment: DeviceEnvironment): DeviceSetup {
  if (isAppleMobile(environment) && !environment.standalone) return 'install';
  if (!environment.pushCapable) return 'unsupported';
  if (environment.permission === 'denied') return 'denied';
  return 'ready';
}
