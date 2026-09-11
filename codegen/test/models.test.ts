import { describe, expect, it } from 'vitest';
import { emit, TASKS_SPEC } from './helpers.js';

describe('generateModels', () => {
  it('generates one pydantic models module per package, required fields first', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['models/tasks/models.py'] ?? '';
    expect(content).toContain('class Task(SpecModel):');
    expect(content).toContain('    id: str\n    title: str\n    status: TaskStatus\n    assignee_id: str | None = None\n    created_at: datetime.datetime | None = None');
    expect(content).toContain('class TaskList(SpecModel):\n    data: list[Task]\n    after: str | None = None\n    before: str | None = None');
    expect(content).toContain('class CreateTaskInput(SpecModel):\n    title: str\n    assignee_id: str | None = None');
    expect(content).toContain('from .enums import TaskStatus');
    expect(content).toContain('from .._base import SpecModel');
    expect(content).toMatch(/__all__ = \[\n    "CreateTaskInput",\n    "Task",\n    "TaskList",\n    "UpdateTaskInput",\n\]/);
    expect(files['models/_base.py']).toContain('class SpecModel(BaseModel):');
  });

  it('re-exports models and enums from the package __init__', async () => {
    const files = await emit(TASKS_SPEC);
    const init = files['models/tasks/__init__.py'] ?? '';
    expect(init).toContain('from .enums import TaskStatus');
    expect(init).toContain('from .models import CreateTaskInput, Task, TaskList, UpdateTaskInput');
    expect(init).toMatch(/__all__ = \[\n    "CreateTaskInput",\n    "Task",\n    "TaskList",\n    "TaskStatus",\n    "UpdateTaskInput",\n\]/);
    expect(files['models/__init__.py']).toContain('Packages: tasks.');
  });

  it('uses wire aliases only when the python name differs', async () => {
    const files = await emit(TASKS_SPEC);
    expect(files['models/tasks/models.py']).not.toContain('Field(');
  });
});
