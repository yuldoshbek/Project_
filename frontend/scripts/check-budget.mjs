/**
 * Бюджет размера сборки.
 *
 * Правило из ADR-0030: начальный JS — не больше 250 КБ в сжатом виде. Это не эстетика.
 * Первый экран на телефоне по 4G должен открываться меньше чем за 2,5 секунды (ТЗ 9), а
 * каждые лишние сто килобайт — это лишняя секунда там, где решение принимают на ходу.
 *
 * Начальный JS — это входной кусок и всё, что он импортирует статически: ровно то, что
 * браузер скачает до первого экрана. Считается по манифесту сборки Vite, а не по папке
 * assets целиком: раздел, вынесенный в отложенный кусок, едет только при переходе в него, и
 * общий счёт по папке наказывал бы именно за то, что бюджет и должен поощрять.
 *
 * Отложенные куски проверяются отдельно: цена перехода в раздел — его кусок вместе с тем,
 * что тот тянет статически сверх начального, и у неё свой предел.
 *
 * Считается gzip, а не сырой размер: по сети едет сжатое, и сырой размер пугает впустую.
 * Падение здесь — не повод поднять предел, а повод посмотреть, что приехало в сборку.
 */

import { gzipSync } from 'node:zlib';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'dist');
const manifestPath = join(dist, '.vite/manifest.json');

const BUDGET_KB = {
    /** Начальный JS: входной кусок и его статические импорты. */
    initialJs: 250,
    /** Начальный CSS. */
    initialCss: 40,
    /** Один переход в раздел: отложенный кусок и его статические импорты сверх начальных. */
    deferredJs: 250,
};

if (!existsSync(manifestPath)) {
    console.error(
        `Нет манифеста сборки: ${manifestPath}.\n` +
            'Без него начальный JS не отличить от отложенного. Проверьте build.manifest в vite.config.ts.',
    );
    process.exit(1);
}

/** @type {Record<string, {file: string, isEntry?: boolean, isDynamicEntry?: boolean, imports?: string[], css?: string[]}>} */
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));

const sizes = new Map();
function gzipKb(file) {
    if (!sizes.has(file)) {
        sizes.set(file, gzipSync(readFileSync(join(dist, file))).length / 1024);
    }
    return sizes.get(file);
}

/** Ключи кусков, которые скачиваются вместе с `start`: он сам и его статические импорты. */
function staticClosure(start, skip = new Set()) {
    const seen = new Set();
    const queue = [start];
    while (queue.length > 0) {
        const key = queue.pop();
        if (seen.has(key) || skip.has(key)) continue;
        seen.add(key);
        queue.push(...(manifest[key]?.imports ?? []));
    }
    return seen;
}

function jsKb(keys) {
    let total = 0;
    for (const key of keys) {
        const { file } = manifest[key];
        if (file.endsWith('.js')) total += gzipKb(file);
    }
    return total;
}

function cssKb(keys) {
    const files = new Set();
    for (const key of keys) {
        for (const file of manifest[key].css ?? []) files.add(file);
    }
    let total = 0;
    for (const file of files) total += gzipKb(file);
    return total;
}

const entries = Object.keys(manifest).filter((key) => manifest[key].isEntry);
if (entries.length === 0) {
    console.error('В манифесте сборки нет входного куска: считать начальный JS не от чего.');
    process.exit(1);
}

const initial = new Set();
for (const entry of entries) {
    for (const key of staticClosure(entry)) initial.add(key);
}

const initialJs = jsKb(initial);
const initialCss = cssKb(initial);

const deferred = Object.keys(manifest)
    .filter((key) => manifest[key].isDynamicEntry && !initial.has(key))
    .map((key) => ({ key, js: jsKb(staticClosure(key, initial)) }))
    .sort((a, b) => b.js - a.js);

const failures = [];
if (initialJs > BUDGET_KB.initialJs) failures.push('начальный JS');
if (initialCss > BUDGET_KB.initialCss) failures.push('начальный CSS');
for (const chunk of deferred) {
    if (chunk.js > BUDGET_KB.deferredJs) failures.push(`отложенный кусок ${chunk.key}`);
}

const lines = [
    `Начальный JS:  ${initialJs.toFixed(1)} КБ из ${BUDGET_KB.initialJs} (кусков: ${initial.size})`,
    `Начальный CSS: ${initialCss.toFixed(1)} КБ из ${BUDGET_KB.initialCss}`,
    deferred.length === 0
        ? 'Отложенных кусков нет.'
        : `Отложенные куски, предел ${BUDGET_KB.deferredJs} КБ на переход:`,
    ...deferred.map((chunk) => `  ${chunk.js.toFixed(1).padStart(6)} КБ  ${chunk.key}`),
];
const report = lines.join('\n');

if (failures.length > 0) {
    console.error(`Сборка вышла за бюджет размера: ${failures.join(', ')}.\n${report}`);
    process.exit(1);
}

console.log(`Бюджет соблюдён.\n${report}`);
