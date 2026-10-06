import { describe, expect, it } from 'vitest';

import { branchStamp } from './stamp';

describe('отпечаток ветви', () => {
  // Тот же вектор проверяет backend (`tests/test_ideas.py`): расчёт в двух местах обязан
  // давать одно и то же, иначе любое удаление ветви получало бы ложный конфликт.
  const a = '00000000-0000-0000-0000-00000000000a';
  const b = '00000000-0000-0000-0000-00000000000b';

  it('совпадает с сервером и не зависит от порядка узлов', () => {
    expect(
      branchStamp([
        { id: a, version: 1 },
        { id: b, version: 2 },
      ]),
    ).toBe('fe20735f');
    expect(
      branchStamp([
        { id: b, version: 2 },
        { id: a, version: 1 },
      ]),
    ).toBe('fe20735f');
    expect(branchStamp([])).toBe('811c9dc5');
  });

  it('меняется от правки узла: версия выросла — отпечаток другой', () => {
    expect(branchStamp([{ id: a, version: 1 }])).not.toBe(branchStamp([{ id: a, version: 2 }]));
  });
});
