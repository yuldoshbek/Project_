/**
 * Что показать на устройстве: на iPhone без экрана «Домой» уведомлений нет вовсе — сначала
 * установка; запрет в настройках кнопкой не снять.
 */

import { describe, expect, it } from 'vitest';

import { deviceSetup, isAppleMobile, type DeviceEnvironment } from './notifications';

const IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';
const IPAD_AS_MAC =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15';
const CHROME =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36';

function env(overrides: Partial<DeviceEnvironment>): DeviceEnvironment {
  return {
    userAgent: CHROME,
    touchPoints: 0,
    standalone: false,
    pushCapable: true,
    permission: 'default',
    ...overrides,
  };
}

describe('deviceSetup', () => {
  it('iPhone в Safari — сначала на экран «Домой»', () => {
    expect(deviceSetup(env({ userAgent: IPHONE, pushCapable: false, permission: null }))).toBe(
      'install',
    );
  });

  it('iPad называет себя «Macintosh», но касаний у него больше одного', () => {
    expect(deviceSetup(env({ userAgent: IPAD_AS_MAC, touchPoints: 5 }))).toBe('install');
    expect(deviceSetup(env({ userAgent: IPAD_AS_MAC, touchPoints: 0 }))).toBe('ready');
  });

  it('с экрана «Домой» — можно включать', () => {
    expect(deviceSetup(env({ userAgent: IPHONE, standalone: true }))).toBe('ready');
  });

  it('браузер без уведомлений и запрет в настройках', () => {
    expect(deviceSetup(env({ pushCapable: false, permission: null }))).toBe('unsupported');
    expect(deviceSetup(env({ permission: 'denied' }))).toBe('denied');
  });

  it('запрет снимается по-разному: в настройках iPhone или в настройках сайта', () => {
    expect(isAppleMobile(env({ userAgent: IPHONE, standalone: true }))).toBe(true);
    expect(isAppleMobile(env({ userAgent: IPAD_AS_MAC, touchPoints: 5 }))).toBe(true);
    expect(isAppleMobile(env({}))).toBe(false);
  });
});
