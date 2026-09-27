/**
 * Примеры разбора строки — они же переедут в тесты домена сервера вместе с правилами.
 *
 * Сегодня в примерах — пятница 25.09.2026: на ней видно правило «день недели — ближайший
 * впереди» и «конец недели — пятница».
 */

import { describe, expect, it } from 'vitest';

import type { Ref, TaskType } from './model';
import { parseLine } from './parse';

const TODAY = '2026-09-25'; // пятница

const PEOPLE: Ref[] = [
  { id: 'p-karimov', name: 'Каримов А.' },
  { id: 'p-yusupova', name: 'Юсупова Д.' },
  { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  { id: 'p-tursunov', name: 'Турсунов Б.' },
  { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
];

const TYPES: TaskType[] = [
  'technical_spec',
  'review_and_endorse',
  'approval',
  'cabinet_submission',
  'analytical_note',
  'site_visit',
  'request_or_survey',
  'subplatform_upload',
  'participant_selection',
  'ijro_report',
  'other',
].map((code) => ({ code, name: code }));

const parse = (text: string) => parseLine(text, { today: TODAY, people: PEOPLE, types: TYPES });

describe('разбор строки задачи', () => {
  it('пример из ТЗ 7: тип, срок и ответственный', () => {
    const result = parse('к пятнице рассмотрение проекта постановления Минэкологии, Каримов');
    expect(result).toEqual({
      title: 'Рассмотрение проекта постановления Минэкологии',
      type_code: 'review_and_endorse',
      due_on: '2026-10-02',
      assignee_id: 'p-karimov',
      matched: { type: 'рассмотр', due: 'к пятнице', assignee: 'Каримов' },
    });
  });

  it.each([
    ['сегодня справка по засухе', '2026-09-25'],
    ['завтра выезд на полигон', '2026-09-26'],
    ['послезавтра запрос в хокимият', '2026-09-27'],
    ['через 3 дня согласование стандарта', '2026-09-28'],
    ['через неделю отбор участников', '2026-10-02'],
    ['через 2 недели ТЗ на группировку', '2026-10-09'],
    ['до среды выгрузка в субплатформу', '2026-09-30'],
    ['в понедельник справка', '2026-09-28'],
    // Сказанное в пятницу «к концу недели» — сегодня.
    ['к концу недели справка', '2026-09-25'],
    ['к концу месяца отчёт', '2026-09-30'],
    ['к 15.10 сведения по поручению', '2026-10-15'],
    ['до 3.03 план работ', '2027-03-03'],
    ['к 15 октября сведения', '2026-10-15'],
    ['10.01.2027 доклад', '2027-01-10'],
  ])('срок: «%s» → %s', (text, due) => {
    expect(parse(text).due_on).toBe(due);
  });

  it.each([
    ['поручить Каримову справку', 'p-karimov'],
    ['справка — Юсуповой', 'p-yusupova'],
    ['Юсупова Д. подготовит проект', 'p-yusupova'],
    ['Рахимов Ш. выезд', 'p-rakhimov'],
    ['отбор участников с Абдуллаевой', 'p-abdullaeva'],
  ])('ответственный: «%s»', (text, id) => {
    expect(parse(text).assignee_id).toBe(id);
  });

  it('ответственный уходит из названия вместе с инициалами', () => {
    expect(parse('Юсупова Д. подготовит проект соглашения').title).toBe(
      'Подготовит проект соглашения',
    );
  });

  it.each([
    ['внести проект в Кабмин', 'cabinet_submission'],
    ['согласовать и внести в Кабинет министров', 'cabinet_submission'],
    ['подготовить ТЗ на платформу', 'technical_spec'],
    ['визирование стандарта', 'review_and_endorse'],
    ['согласование с Минфином', 'approval'],
    ['аналитическая справка для АП', 'analytical_note'],
    ['командировка в Навои', 'site_visit'],
    ['опросник для хокимиятов', 'request_or_survey'],
    ['выгрузка данных', 'subplatform_upload'],
    ['отбор пилотных районов', 'participant_selection'],
    ['сведения по поручению ПФ-155', 'ijro_report'],
    ['позвонить в министерство', null],
  ])('тип: «%s» → %s', (text, code) => {
    expect(parse(text).type_code).toBe(code);
  });

  it('без срока и ответственного — только название', () => {
    expect(parse('  позвонить в министерство.  ')).toMatchObject({
      title: 'Позвонить в министерство',
      due_on: null,
      assignee_id: null,
    });
  });

  it('несуществующая дата — не срок', () => {
    expect(parse('к 31.02 отчёт').due_on).toBeNull();
  });
});
