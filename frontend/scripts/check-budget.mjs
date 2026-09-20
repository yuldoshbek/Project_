/**
 * Бюджет размера сборки.
 *
 * Правило из ADR-0030: начальный JS — не больше 250 КБ в сжатом виде. Это не эстетика.
 * Первый экран на телефоне по 4G должен открываться меньше чем за 2,5 секунды (ТЗ 9), а
 * каждые лишние сто килобайт — это лишняя секунда там, где решение принимают на ходу.
 *
 * Считается gzip, а не сырой размер: по сети едет сжатое, и сырой размер пугает впустую.
 * Падение здесь — не повод поднять предел, а повод посмотреть, что приехало в сборку.
 */

import { gzipSync } from 'node:zlib';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const assets = join(root, 'dist/assets');

const BUDGET_KB = { js: 250, css: 40 };

function gzipKb(file) {
    return gzipSync(readFileSync(file)).length / 1024;
}

let js = 0;
let css = 0;

for (const name of readdirSync(assets)) {
    const size = gzipKb(join(assets, name));
    if (name.endsWith('.js')) js += size;
    if (name.endsWith('.css')) css += size;
}

const report = [
    `JS:  ${js.toFixed(1)} КБ из ${BUDGET_KB.js}`,
    `CSS: ${css.toFixed(1)} КБ из ${BUDGET_KB.css}`,
].join('\n');

if (js > BUDGET_KB.js || css > BUDGET_KB.css) {
    console.error(`Сборка вышла за бюджет размера.\n${report}`);
    process.exit(1);
}

console.log(`Бюджет соблюдён.\n${report}`);
