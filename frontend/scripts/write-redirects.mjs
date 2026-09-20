// Пишет dist/_redirects: прокси /api на API этого развёртывания и возврат оболочки
// приложения на все остальные пути.
//
// Почему не в netlify.toml: адрес API у рабочей системы, у каждого превью и у машины
// разработчика разный, а netlify.toml один и в него переменные не подставляются. Ошибка
// здесь означает, что превью смотрит в чужую базу, поэтому скрипт падает молча только в
// разработке, а на площадке требует адрес явно.

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const target = resolve(root, 'dist/_redirects');

const origin = process.env.ORBITA_API_ORIGIN?.replace(/\/+$/, '');
// Требуем адрес там, где сборка действительно куда-то выкладывается: на самой Netlify
// и в шагах выкладки конвейера. Обычная проверочная сборка в CI собирается без адреса.
const mustHaveOrigin = Boolean(process.env.NETLIFY || process.env.ORBITA_REQUIRE_API_ORIGIN);

if (!origin && mustHaveOrigin) {
    console.error(
        'Не задан ORBITA_API_ORIGIN. Без него интерфейс будет обращаться к собственному ' +
            'адресу и получать 404 вместо данных. Значение — адрес API этого развёртывания.',
    );
    process.exit(1);
}

const apiOrigin = origin ?? 'http://localhost:8000';

const rules = [
    '# Файл создан frontend/scripts/write-redirects.mjs при сборке. Править вручную незачем.',
    `/api/*  ${apiOrigin}/api/:splat  200`,
    '/*      /index.html              200',
    '',
].join('\n');

mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, rules, 'utf8');
console.log(`_redirects: /api → ${apiOrigin}`);
