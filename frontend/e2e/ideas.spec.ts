/**
 * Идеи и карты (`sections/ideas/`) — на настоящем API (`/api/v1/ideas…`, `/api/v1/maps…`) и
 * вымышленных данных базы (`backend/app/demo_ideas.py`).
 *
 * 1. Раздел на трёх устройствах в двух темах, без горизонтальной прокрутки.
 * 2. Идея превращается в проект одним действием (критерий 1 блока 3).
 * 3. Карта: полотно на ноутбуке — узел добавляется и перетаскивается; контур на телефоне;
 *    на мониторе правки нет; правка помощника видна руководителю без перезагрузки.
 */

import { expect, test, type Page } from '@playwright/test';

import { branchStamp } from '../src/sections/ideas/stamp';

import { REPORT_DIR, issueLink } from './link';

const SIZES = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'laptop', width: 1440, height: 900 },
  { name: 'monitor', width: 2560, height: 1440 },
] as const;

const THEMES = ['light', 'dim'] as const;
const MAP = 'Мониторинг сельского хозяйства';

let leader: string;
let assistant: string;

test.beforeAll(() => {
  leader = issueLink('leader');
  assistant = issueLink('assistant');
});

async function open(
  page: Page,
  link: string,
  path = '/ideas',
  theme: (typeof THEMES)[number] = 'light',
) {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto(path);
  await expect(page.getByRole('heading', { name: 'Идеи и карты', level: 1 })).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

interface BoardNode {
  id: string;
  parent_id: string | null;
  text: string;
  x: number;
  version: number;
}

async function readBoard(page: Page, mapId: string | null): Promise<BoardNode[]> {
  const board = (await (await page.request.get(`/api/v1/maps/${mapId}`)).json()) as {
    node_list: BoardNode[];
  };
  return board.node_list;
}

/**
 * Узел, заведённый сценарием, убирается за собой — и когда сценарий упал (вызов стоит в
 * `finally`): снимки следующего прогона — без него. Проверка мягкая: сбой уборки виден в
 * отчёте, но не заслоняет ошибку самого сценария.
 */
async function removeNode(page: Page, mapId: string | null, text: string) {
  const nodes = await readBoard(page, mapId);
  const node = nodes.find((each) => each.text === text);
  if (!node) return;
  // Сервер убирает ветвь, только если она такая, какой её видели: узлы и их версии.
  const branch = new Set([node.id]);
  for (let grew = true; grew;) {
    grew = false;
    for (const each of nodes) {
      if (each.parent_id && branch.has(each.parent_id) && !branch.has(each.id)) {
        branch.add(each.id);
        grew = true;
      }
    }
  }
  const response = await page.request.delete(`/api/v1/maps/${mapId}/nodes/${node.id}`, {
    params: {
      version: node.version,
      branch: branchStamp(nodes.filter((each) => branch.has(each.id))),
    },
  });
  expect.soft(response.ok(), `узел «${text}» не убран: ${response.status()}`).toBe(true);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Идеи: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await open(page, leader, '/ideas', theme);
      await expect(page.getByRole('heading', { name: 'Что ждёт моего «да»?' })).toBeVisible();
      await page.screenshot({
        path: `${REPORT_DIR}/ideas-${size.name}-${theme}.png`,
        animations: 'disabled',
      });
      await noOverflow(page);

      await page.getByRole('tab', { name: 'Карты' }).click();
      await page.getByRole('button', { name: new RegExp(MAP) }).click();
      await expect(page.getByRole('heading', { name: MAP })).toBeVisible();
      await page.screenshot({
        path: `${REPORT_DIR}/ideas-map-${size.name}-${theme}.png`,
        animations: 'disabled',
      });
      await noOverflow(page);
    });
  }
}

// Идея и выросший из неё проект остаются в базе разработки: в API нет удаления ни идей, ни
// проектов (`backend/app/api/routes/ideas.py`, `projects.py`) — решение и запись, которую оно
// завело, история не теряет (инвариант 5). Снимки раздела в этом файле идут раньше (порядок
// файла, один исполнитель), поэтому первый прогон снимает раздел без следов сценария; на
// повторных прогонах строки «Снимки для учебников географии …» копятся в «Решено». Чистую
// картину даёт база, заведённая заново (`make reset`, миграции, справочники, `make demo`), а
// не уборка из сценария.
test('идея превращается в проект одним действием — с телефона руководителя', async ({
  browser,
}) => {
  const text = `Снимки для учебников географии ${Date.now()}`;
  const writer = await browser.newPage();
  await open(writer, assistant);
  await writer.getByLabel('Идея').fill(text);
  await writer.getByRole('button', { name: 'Записать' }).click();
  const draft = writer.getByRole('listitem').filter({ hasText: text });
  await draft.getByRole('button', { name: 'На рассмотрение' }).click();
  await expect(
    writer.getByRole('region', { name: 'На рассмотрении' }).getByText(text),
  ).toBeVisible();
  await writer.close();

  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await open(page, leader);
  const row = page
    .getByRole('region', { name: 'На рассмотрении' })
    .getByRole('listitem')
    .filter({ hasText: text });
  await row.getByRole('button', { name: 'Решить' }).click();
  const sheet = page.getByRole('dialog', { name: 'Решение по идее' });
  await expect(sheet.getByText(text)).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/ideas-decision-phone-light.png`,
    animations: 'disabled',
  });
  await sheet.getByRole('button', { name: 'В проект' }).click();
  await expect(sheet).toBeHidden();
  const decided = page
    .getByRole('region', { name: 'Решено' })
    .getByRole('listitem')
    .filter({ hasText: text });
  await expect(decided.getByText(/^Проект /)).toBeVisible();
  await noOverflow(page);
  await page.close();
});

test('ноутбук: узел добавляется под выбранным и перетаскивается', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, assistant, '/ideas?view=maps');
  await page.getByRole('button', { name: new RegExp(MAP) }).click();
  const canvas = page.getByRole('region', { name: 'Полотно карты' });
  await expect(canvas.getByText('не связан').first()).toBeVisible();
  const mapId = new URL(page.url()).searchParams.get('map');
  const text = `Узел ${Date.now()}`;

  try {
    await canvas.getByRole('button', { name: 'Пастбища', exact: true }).click();
    await page.getByLabel('Новый узел под «Пастбища»').fill(text);
    await page.getByRole('button', { name: 'Добавить узел' }).click();
    const node = canvas.getByRole('button', { name: text, exact: true });
    await expect(node).toBeVisible();

    // «Под выбранным» — родитель ушёл в запрос, а не только стоит в подписи поля.
    const nodes = await readBoard(page, mapId);
    const added = nodes.find((each) => each.text === text);
    const pasture = nodes.find((each) => each.text === 'Пастбища');
    expect(added?.parent_id, 'родитель нового узла').toBe(pasture?.id);
    const start = added?.x ?? 0;

    await node.scrollIntoViewIfNeeded();
    const before = await node.boundingBox();
    if (!before) throw new Error('узла нет на полотне');
    await page.mouse.move(before.x + 20, before.y + 20);
    await page.mouse.down();
    await page.mouse.move(before.x + 140, before.y + 80, { steps: 8 });
    await page.mouse.up();
    await expect
      .poll(async () => (await node.boundingBox())?.x ?? 0)
      .toBeGreaterThan(before.x + 100);

    // Место узла сохранено на сервере, а не только на экране.
    const saved = async () =>
      (await readBoard(page, mapId)).find((each) => each.text === text)?.x ?? 0;
    await expect.poll(saved).toBeGreaterThan(start + 100);
    await page.screenshot({
      path: `${REPORT_DIR}/ideas-canvas-laptop-light.png`,
      animations: 'disabled',
    });
  } finally {
    await removeNode(page, mapId, text);
  }
});

test('правка помощника видна руководителю без перезагрузки', async ({ browser }) => {
  const watcher = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const editor = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const text = `Живая правка ${Date.now()}`;
  let mapId: string | null = null;
  try {
    await open(watcher, leader, '/ideas?view=maps');
    await watcher.getByRole('button', { name: /Космическое образование/ }).click();
    const watched = watcher.getByRole('region', { name: 'Полотно карты' });
    await expect(
      watched.getByRole('button', { name: 'Космическое образование', exact: true }),
    ).toBeVisible();

    await open(editor, assistant, '/ideas?view=maps');
    await editor.getByRole('button', { name: /Космическое образование/ }).click();
    await expect(editor.getByRole('region', { name: 'Полотно карты' })).toBeVisible();
    mapId = new URL(editor.url()).searchParams.get('map');
    await editor.getByLabel('Новый узел верхнего уровня').fill(text);
    await editor.getByRole('button', { name: 'Добавить узел' }).click();
    await expect(editor.getByRole('button', { name: text })).toBeVisible();

    // Опрос раз в 5 с (ADR-0034): узел появляется у второго без перезагрузки.
    await expect(watched.getByRole('button', { name: text })).toBeVisible({ timeout: 12_000 });
  } finally {
    if (mapId) await removeNode(editor, mapId, text);
    await watcher.close();
    await editor.close();
  }
});

test('телефон — контур, монитор — без правки', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, leader, '/ideas?view=maps');
  await page.getByRole('button', { name: new RegExp(MAP) }).click();
  await expect(page.getByRole('region', { name: 'Контур карты' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Полотно карты' })).toHaveCount(0);
  await page.screenshot({
    path: `${REPORT_DIR}/ideas-outline-phone-light.png`,
    animations: 'disabled',
  });

  await page.setViewportSize({ width: 2560, height: 1440 });
  await expect(page.getByRole('region', { name: 'Полотно карты' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Добавить узел' })).toHaveCount(0);

  // Идеи на мониторе: решение руководителя есть, записи и правки нет (ТЗ 6).
  await page.getByRole('tab', { name: 'Идеи' }).click();
  await expect(page.getByRole('heading', { name: 'Что ждёт моего «да»?' })).toBeVisible();
  await expect(page.getByLabel('Идея', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'На рассмотрение' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Изменить' })).toHaveCount(0);
});
