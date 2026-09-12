import { describe, expect, it } from 'vitest';
import { emit, emitInline, TASKS_SPEC } from './helpers.js';

const FIXTURE = `
openapi: "3.1.0"
info: { title: Fixture API, version: "1.0.0" }
servers: [{ url: https://api.example.com }]
components:
  schemas:
    Widget:
      type: object
      required: [id, kind]
      properties:
        note: { type: string }
        id: { type: string }
        nickname: { type: string, nullable: true }
        kind: { $ref: "#/components/schemas/Kind" }
        createdAt: { type: string, format: date-time }
        tags: { type: array, items: { type: string } }
        count: { type: integer, nullable: true }
    Kind:
      type: string
      enum: [big, small, "2xl", in-between]
    Priority:
      type: integer
      enum: [1, 2, 3]
paths:
  /widgets:
    get:
      operationId: listWidgets
      tags: [Widgets]
      parameters:
        - { name: kind, in: query, schema: { $ref: "#/components/schemas/Kind" } }
        - { name: priority, in: query, schema: { $ref: "#/components/schemas/Priority" } }
      responses:
        "200":
          content:
            application/json:
              schema: { type: array, items: { $ref: "#/components/schemas/Widget" } }
`;

describe('generateModels', () => {
  it('orders required fields first and keeps the spec order within each group', async () => {
    const files = await emitInline(FIXTURE);
    const content = files['models/widgets/__init__.py'] ?? '';
    const cls = content.slice(content.indexOf('class Widget('));
    expect(cls).toContain('class Widget(SpecModel):\n    id: str\n    kind: Kind\n    note: str | None = None\n    nickname: str | None = None\n');
    expect(cls.indexOf('    id: str')).toBeLessThan(cls.indexOf('    note: str'));
  });

  it('renders nullable and optional-but-not-nullable fields as `X | None = None`, without doubling None', async () => {
    const files = await emitInline(FIXTURE);
    const content = files['models/widgets/__init__.py'] ?? '';
    expect(content).toContain('    nickname: str | None = None'); // nullable in the spec
    expect(content).toContain('    tags: list[str] | None = None'); // optional, not nullable
    expect(content).toContain('    count: int | None = None'); // both
    expect(content).not.toContain('None | None');
  });

  it('uses snake_case attributes with the wire name as alias only when they differ', async () => {
    const files = await emitInline(FIXTURE);
    const content = files['models/widgets/__init__.py'] ?? '';
    expect(content).toContain('    created_at: datetime.datetime | None = Field(default=None, alias="createdAt")');
    expect(content).toContain('from pydantic import Field');
    expect(content).toContain('import datetime');
    const tasks = await emit(TASKS_SPEC);
    expect(tasks['models/tasks/__init__.py']).not.toContain('Field(');
  });

  it('emits str and int enums with a __str__ that yields the value', async () => {
    const files = await emitInline(FIXTURE);
    const content = files['models/widgets/enums.py'] ?? '';
    expect(content).toContain('class Kind(str, Enum):\n    BIG = "big"\n    SMALL = "small"\n    V_2XL = "2xl"\n    IN_BETWEEN = "in-between"\n\n    __str__ = str.__str__');
    expect(content).toContain('class Priority(int, Enum):\n    V_1 = 1\n    V_2 = 2\n    V_3 = 3\n\n    __str__ = int.__str__');
    expect(content).toMatch(/__all__ = \[\n    "Kind",\n    "Priority",\n\]/);
  });

  it('marks enum members named like credentials for bandit', async () => {
    const files = await emitInline(FIXTURE.replace('enum: [big, small, "2xl", in-between]', 'enum: [big, NextToken, password]'));
    const content = files['models/widgets/enums.py'] ?? '';
    expect(content).toContain('    BIG = "big"\n    NEXT_TOKEN = "NextToken"  # nosec B105\n    PASSWORD = "password"  # nosec B105');
  });

  it('puts every model of a package in its __init__.py, enums in enums.py, and re-exports both', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['models/tasks/__init__.py'] ?? '';
    expect(content).toContain('from __future__ import annotations');
    expect(content).toContain('from .._base import SpecModel');
    expect(content).toContain('from .enums import TaskStatus');
    expect(content).toContain('class Task(SpecModel):\n    id: str\n    title: str\n    status: TaskStatus\n    assignee_id: str | None = None\n    created_at: datetime.datetime | None = None');
    expect(content).toContain('class TaskList(SpecModel):\n    data: list[Task]\n    after: str | None = None\n    before: str | None = None');
    expect(content).toMatch(/__all__ = \[\n    "CreateTaskInput",\n    "Task",\n    "TaskList",\n    "TaskStatus",\n    "UpdateTaskInput",\n\]/);
    expect(files['models/_base.py']).toContain('class SpecModel(BaseModel):');
    expect(files['models/__init__.py']).toContain('Packages: tasks.');
    expect(Object.keys(files).filter((p) => p.startsWith('models/tasks/')).sort()).toEqual(['models/tasks/__init__.py', 'models/tasks/enums.py']);
  });
});
