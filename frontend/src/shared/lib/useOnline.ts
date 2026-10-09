/**
 * Есть ли связь — по событиям браузера `online` и `offline`.
 *
 * `navigator.onLine` говорит правду о выключенной сети (самолёт, лифт), но не о плохой: при
 * слабой связи он `true`. Поэтому это только подсказка к пометке «нет связи», а не условие
 * запросов — запросы и их отказы живут своей жизнью.
 */

import { useSyncExternalStore } from 'react';

function subscribe(onChange: () => void): () => void {
  window.addEventListener('online', onChange);
  window.addEventListener('offline', onChange);
  return () => {
    window.removeEventListener('online', onChange);
    window.removeEventListener('offline', onChange);
  };
}

export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  );
}
