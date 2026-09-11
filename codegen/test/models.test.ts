import { describe, expect, it } from 'vitest';
import { emit, TASKS_SPEC } from './helpers.js';

describe('generateModels', () => {
  it('generates pydantic models and Literal enums from the tasks spec', async () => {
    const files = await emit(TASKS_SPEC, 'tasks', 'v1');
    const content = files['models/tasks/v1.py'] ?? '';
    expect(content).not.toBe('');
    expect(content).toContain('TaskStatus: TypeAlias = Literal["pending", "in_progress", "done", "cancelled"]');
    expect(content).toContain('class Task(SpecModel):');
    expect(content).toContain('    id: str\n');
    expect(content).toContain('    title: str\n');
    expect(content).toContain('    status: TaskStatus\n');
    expect(content).toContain('    assignee_id: str | None = None');
    expect(content).toContain('    created_at: datetime.datetime | None = None');
    expect(content).toContain('class TaskList(SpecModel):\n    data: list[Task]\n    after: str | None = None');
    expect(content).toContain('class CreateTaskInput(SpecModel):\n    title: str\n    assignee_id: str | None = None');
    expect(content).toContain('class UpdateTaskInput(SpecModel):\n    title: str | None = None');
    // required fields precede optional ones inside a class
    const task = content.slice(content.indexOf('class Task(SpecModel):'), content.indexOf('class TaskList(SpecModel):'));
    expect(task.indexOf('    id: str')).toBeLessThan(task.indexOf('    assignee_id: str | None'));
    expect(content).toMatch(/__all__ = \[\n    "CreateTaskInput",\n    "Task",\n    "TaskList",\n    "TaskStatus",\n    "UpdateTaskInput",\n\]/);
  });

  it('adds wire aliases only when the python name differs', async () => {
    const files = await emit(TASKS_SPEC, 'tasks', 'v1');
    expect(files['models/tasks/v1.py']).not.toContain('Field(');
  });
});
