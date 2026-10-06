/**
 * Замер первого экрана на телефоне (критерий 4 блока 3: меньше 2,5 с по 4G).
 *
 * Условия — два профиля сети (ниже, `PROFILES`) и процессор, замедленный вчетверо. «Первый
 * экран» — Пульт с вопросом руководителя и первой строкой лестницы: то, ради чего его
 * открывают. Два случая: холодный вход (новый контекст браузера: кеш пуст, соединение новое)
 * и повторный (тот же контекст сразу после холодного: файлы сборки из кеша — они с отпечатком
 * в имени, — соединение уже открыто). Сессия в обоих случаях уже есть: меряется открытие
 * Пульта, а не переход по ссылке.
 *
 * Мерить нужно рабочую сборку (сервер агентства или выкладку), а не сервер разработки:
 * у Vite без сборки сотни модулей вместо одного куска.
 *
 *   ORBITA_URL=https://orbita.agency.uz ORBITA_LINK=<личная ссылка> node scripts/measure-first-screen.mjs
 *
 * Ссылку передают переменной окружения, чтобы она не осталась в истории оболочки и в логах;
 * сам скрипт её не печатает, в том числе в тексте ошибок Playwright.
 */

import { chromium, devices } from 'playwright';

const base = process.env.ORBITA_URL ?? 'http://localhost:8088';
const link = process.env.ORBITA_LINK;
const budgetMs = 2500;
const runs = Number(process.env.ORBITA_RUNS ?? 3);
if (!link) {
    console.error('Нужна ORBITA_LINK — личная ссылка руководителя.');
    process.exit(2);
}

// Профили сети — пресеты Chrome DevTools «Slow 4G» и «Fast 4G» на том же механизме CDP,
// числа один в один: devtools-frontend, front_end/core/sdk/NetworkManager.ts,
// Slow4GConditions и Fast4GConditions (сверено 05.10.2026). Мегабит там — 1000 × 1000 бит.
// Эмуляция CDP задерживает запрос целиком, а не пакеты, поэтому RTT пресета умножен на 3,75
// и 2,75, а пропускная способность — на 0,9: без поправки эмуляция оптимистичнее настоящей
// сети (те же поправки у Lighthouse в режиме devtools — GoogleChrome/lighthouse#7330).
// Первая версия скрипта брала голые 150 и 60 мс и на каждом последовательном круге запросов
// недосчитывала около 410 и 105 мс.
//
// «Slow 4G» — мобильный профиль Lighthouse по умолчанию, по сути хороший 3G: по нему бюджет
// проверяется строже. «Fast 4G» ближе к 4G в городе, по его холодному входу и решается
// критерий (V50). Процессор замедлен вчетверо в обоих.
const PROFILES = {
    'slow-4g': {
        offline: false,
        latency: 150 * 3.75,
        downloadThroughput: ((1.6 * 1000 * 1000) / 8) * 0.9,
        uploadThroughput: ((750 * 1000) / 8) * 0.9,
    },
    'fast-4g': {
        offline: false,
        latency: 60 * 2.75,
        downloadThroughput: ((9 * 1000 * 1000) / 8) * 0.9,
        uploadThroughput: ((1.5 * 1000 * 1000) / 8) * 0.9,
    },
};
const DECIDING_PROFILE = 'fast-4g';

// Рабочий файл PWA отключён: иначе после входа файлы сборки отдаёт он, мимо замедленной
// сети, и «первый вход» перестаёт быть первым (так и вышло в первом замере).
const phone = {
    ...devices['iPhone 13'],
    viewport: { width: 390, height: 844 },
    serviceWorkers: 'block',
};

// Playwright пишет в текст ошибки адрес перехода, а адрес здесь — личная ссылка. Прячется
// и сама ссылка, и её последний сегмент: браузер мог показать адрес в другом написании.
const secrets = [link];
try {
    const token = new URL(link).pathname.split('/').filter(Boolean).pop();
    if (token && token.length >= 8) secrets.push(token);
} catch {
    // Не адрес — тогда переход упадёт сам, а прятать достаточно строку целиком.
}
const hide = (text) =>
    secrets.reduce((result, secret) => result.replaceAll(secret, '<ORBITA_LINK>'), text);

/** Вход по ссылке — без замедления и в отдельном контексте; наружу уходит только сессия. */
async function signIn(browser) {
    const context = await browser.newContext(phone);
    try {
        const page = await context.newPage();
        await page.goto(link);
        await page.waitForURL((url) => !url.pathname.startsWith('/api/access'));
        return await context.storageState();
    } catch (error) {
        throw new Error(`Вход по ORBITA_LINK не удался: ${hide(String(error?.message ?? error))}`);
    } finally {
        await context.close();
    }
}

async function measure(context, network) {
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions', network);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    const started = Date.now();
    await page.goto(`${base}/`, { waitUntil: 'commit' });
    // Язык хранится у пользователя на сервере (блок 3): надписи ищутся на всех трёх языках,
    // иначе замер руководителя с узбекским интерфейсом ждал бы русский экран до таймаута.
    await page
        .getByRole('heading', { name: /^(Пульт|Pult)$/, level: 1 })
        .waitFor({ timeout: 30000 });
    await page
        .getByRole('button', { name: /Показать только|Faqat koʻrsatish|Фақат кўрсатиш/ })
        .first()
        .waitFor({ timeout: 30000 });
    const elapsed = Date.now() - started;
    // По описанию протокола эмуляция задерживает ответ после отправки запроса, а DNS, TCP и
    // TLS проходят со скоростью настоящей сети машины. Их время для документа печатается
    // рядом, чтобы было видно, сколько настоящего соединения сидит в цифре.
    const handshake = await page.evaluate(() => {
        const [navigation] = performance.getEntriesByType('navigation');
        return navigation ? Math.round(navigation.connectEnd - navigation.domainLookupStart) : 0;
    });
    await page.close();
    return { elapsed, handshake };
}

const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
const verdict = (ms) =>
    ms <= budgetMs ? `в бюджете ${budgetMs} мс` : `ВНЕ БЮДЖЕТА ${budgetMs} мс`;
const mbit = (bytesPerSecond) =>
    ((bytesPerSecond * 8) / 1000 / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 2 });
const summary = (values) => `медиана ${median(values)} мс (${values.join(', ')})`;

const browser = await chromium.launch();
let failed = false;
try {
    const storageState = await signIn(browser);
    console.log(
        `Первый экран ${base}/ — от перехода до заголовка Пульта и первой строки лестницы.`,
    );
    console.log(
        'iPhone 13 (390×844), процессор медленнее вчетверо, рабочий файл PWA отключён, сессия уже открыта.',
    );
    console.log(
        `Сеть — пресеты Chrome DevTools, задержка добавляется к каждому запросу. Решает холодный вход по ${DECIDING_PROFILE}.`,
    );
    for (const [profile, network] of Object.entries(PROFILES)) {
        const cold = [];
        const handshakes = [];
        const warm = [];
        for (let run = 0; run < runs; run += 1) {
            // Новый контекст на каждый холодный замер: у контекста свои кеш, соединения и
            // сессии TLS. Первая версия чистила только кеш во вкладке того же контекста, где
            // прошёл вход, и соединение оставалось тёплым. Кеш DNS самой системы скрипт не
            // сбрасывает.
            const context = await browser.newContext({ ...phone, storageState });
            try {
                const first = await measure(context, network);
                cold.push(first.elapsed);
                handshakes.push(first.handshake);
                warm.push((await measure(context, network)).elapsed);
            } finally {
                await context.close();
            }
        }
        console.log(
            `\n${profile}: задержка ${network.latency} мс на запрос, вниз ${mbit(network.downloadThroughput)} Мбит/с, вверх ${mbit(network.uploadThroughput)} Мбит/с`,
        );
        console.log(
            `  холодный вход (новый контекст: кеш пуст, соединение новое): ${summary(cold)} — ${verdict(median(cold))}`,
        );
        console.log(
            `    в том числе DNS, TCP и TLS документа по настоящей сети машины, без эмуляции: ${summary(handshakes)}`,
        );
        console.log(
            `  повторный вход (тот же контекст: файлы сборки из кеша, соединение открыто): ${summary(warm)} — ${verdict(median(warm))}`,
        );
        if (profile === DECIDING_PROFILE && median(cold) > budgetMs) failed = true;
    }
} finally {
    await browser.close();
}
if (failed) process.exit(1);
