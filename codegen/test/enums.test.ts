import { describe, expect, it } from 'vitest';
import { renderEnum } from '../src/python/enums.js';
import { emit, TASKS_SPEC } from './helpers.js';

describe('generateEnums', () => {
  it('renders str enums with upper-snake members', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['models/tasks/enums.py'] ?? '';
    expect(content).toContain('from enum import Enum');
    expect(content).toContain('class TaskStatus(str, Enum):\n    PENDING = "pending"\n    IN_PROGRESS = "in_progress"\n    DONE = "done"\n    CANCELLED = "cancelled"');
    expect(content).toContain('__all__ = [\n    "TaskStatus",\n]');
  });

  it('keeps members unique and valid python identifiers', () => {
    const lines = renderEnum({ name: 'X', values: [{ name: 'a', value: 'I' }, { name: 'b', value: '1st' }, { name: 'c', value: 'Foo Bar' }, { name: 'd', value: 'foo-bar' }] }, 'X');
    expect(lines).toEqual(['class X(str, Enum):', '    I_ = "I"', '    V_1ST = "1st"', '    FOO_BAR = "Foo Bar"', '    FOO_BAR_2 = "foo-bar"']);
    expect(renderEnum({ name: 'N', values: [{ name: 'one', value: 1 }, { name: 'two', value: 2 }] }, 'N')).toEqual(['class N(int, Enum):', '    V_1 = 1', '    V_2 = 2']);
  });
});
