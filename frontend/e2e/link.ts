/**
 * Личная ссылка для сценариев.
 *
 * Ссылку выпускает то же средство, которым пользуется человек после первой выкладки
 * (`python -m app.access_cli`). Подменять вход в тестах нельзя: тогда на всём наборе не
 * проверялось бы единственное, что отделяет систему от чужой вкладки (ADR-0029).
 *
 * Ссылка берётся **своя на каждый файл сценариев**, а не одна на прогон. Причина в самом
 * правиле, которое мы проверяем: перевыпуск гасит прежние сессии, и общая ссылка после
 * такого сценария перестала бы работать у соседних — падали бы они, а причина была бы не
 * в них.
 */

import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

/**
 * Куда складываются снимки и PDF: папка отчёта текущего блока. Доказательства прошлого
 * блока не перезаписываются — прежде снимки блока 1 затёрли бы снимки блока 0.
 */
export const REPORT_DIR = resolve(
  here,
  `../../docs/reports/${process.env.ORBITA_E2E_BLOCK ?? 'block-1'}`,
);
const backend = resolve(here, '../../backend');

export function issueLink(role: 'assistant' | 'leader' = 'assistant'): string {
  const baseURL = process.env.ORBITA_E2E_URL ?? 'http://localhost:5173';
  const output = execFileSync(
    'uv',
    ['run', 'python', '-m', 'app.access_cli', role, '--base-url', baseURL],
    { cwd: backend, encoding: 'utf8' },
  );

  const link = output.trim().split('\n').pop();
  if (!link?.startsWith('http')) {
    throw new Error(`не удалось выпустить ссылку доступа: ${output}`);
  }
  return link;
}
