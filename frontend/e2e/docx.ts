/**
 * Таблица Word для сценария загрузки «Ижро» — собирается в памяти.
 *
 * Файлы `.docx` в репозиторий не попадают (`.gitignore`: настоящие таблицы — данные
 * агентства), поэтому образец строится кодом: архив без сжатия с одним `document.xml` той же
 * разметки, что у «Назорат жадвали» (абзацы в ячейках, семь граф). Разбирает его сервер
 * (`backend/app/domain/ijro_import.py`) — как настоящий.
 */

import { crc32 } from 'node:zlib';

const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';

const HEADER = [
  '№',
  'Ҳужжат тури ва рақами',
  'Топшириқ мазмуни',
  'Ижро муддати',
  'Масъул ижрочи',
  'Ижро ҳолати',
  'Изоҳ',
];

const MONTHS = [
  'январь',
  'февраль',
  'март',
  'апрель',
  'май',
  'июнь',
  'июль',
  'август',
  'сентябрь',
  'октябрь',
  'ноябрь',
  'декабрь',
];

/** Срок, как его пишет источник: «25 декабрь», без года. */
export function dueCell(day: string): string {
  const [, month, date] = day.split('-').map(Number);
  return `${date} ${MONTHS[(month ?? 1) - 1]}`;
}

export interface TableRow {
  document: string;
  content: string;
  due: string;
  responsible: string;
}

function escape(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const paragraph = (text: string) =>
  `<w:p><w:r><w:t xml:space="preserve">${escape(text)}</w:t></w:r></w:p>`;

const cells = (values: string[]) =>
  `<w:tr>${values.map((value) => `<w:tc>${value ? paragraph(value) : '<w:p/>'}</w:tc>`).join('')}</w:tr>`;

function zip(name: string, content: Buffer): Buffer {
  const file = Buffer.from(name, 'utf8');
  const sum = crc32(content);
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4);
  local.writeUInt16LE(0x0800, 6); // имя в UTF-8
  local.writeUInt16LE(0, 8); // без сжатия
  local.writeUInt16LE(0x21, 12); // 01.01.1980
  local.writeUInt32LE(sum, 14);
  local.writeUInt32LE(content.length, 18);
  local.writeUInt32LE(content.length, 22);
  local.writeUInt16LE(file.length, 26);
  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4);
  central.writeUInt16LE(20, 6);
  central.writeUInt16LE(0x0800, 8);
  central.writeUInt16LE(0x21, 14);
  central.writeUInt32LE(sum, 16);
  central.writeUInt32LE(content.length, 20);
  central.writeUInt32LE(content.length, 24);
  central.writeUInt16LE(file.length, 28);
  const records = Buffer.concat([local, file, content]);
  const directory = Buffer.concat([central, file]);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(1, 8);
  end.writeUInt16LE(1, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(records.length, 16);
  return Buffer.concat([records, directory, end]);
}

/** Файл `.docx` с заголовком «… Назорат жадвали {год} йил» и одной таблицей. */
export function controlTable(year: number, rows: TableRow[]): Buffer {
  const body =
    paragraph(`1. ПА Назорат жадвали ${year} йил`) +
    '<w:tbl>' +
    cells(HEADER) +
    rows
      .map((row, index) =>
        cells([String(index + 1), row.document, row.content, row.due, row.responsible, '', '']),
      )
      .join('') +
    '</w:tbl>';
  const xml = `<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="${W}"><w:body>${body}</w:body></w:document>`;
  return zip('word/document.xml', Buffer.from(xml, 'utf8'));
}
