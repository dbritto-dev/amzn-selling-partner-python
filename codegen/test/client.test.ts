import { describe, expect, it } from 'vitest';
import { latestAliases } from '../src/python/client.js';
import { emit, TASKS_SPEC } from './helpers.js';

describe('generateClient', () => {
  it('renders the namespace class with one lazy resource per service', async () => {
    const files = await emit(TASKS_SPEC, 'TasksClient');
    const content = files['client.py'] ?? '';
    expect(content).toContain('class TasksClient:');
    expect(content).toContain('class AsyncTasksClient:');
    expect(content).toContain('base_url: str = "https://api.tasks.example.com",');
    expect(content).toContain('self._http = HttpClient(');
    expect(content).toContain('    @cached_property\n    def tasks(self) -> TasksClient:\n        from .resources.tasks import TasksClient\n\n        return TasksClient(self._http)');
    expect(content).toContain('    from .resources.tasks import AsyncTasksClient, TasksClient');
    expect(content).toContain('__all__ = ["AsyncTasksClient", "TasksClient"]');
  });

  it('adds a latest-version alias per API and the configured aliases', () => {
    const aliases = latestAliases(['orders_v0', 'orders_v2026_01_01', 'shipping_v1', 'shipping_v2', 'sellers_v1', 'invoices_api_model_v2024_06_19'], { invoices: 'invoices_api_model', sellers: 'sellers_v1' });
    expect([...aliases.entries()]).toEqual([
      ['invoices', 'invoices_api_model_v2024_06_19'],
      ['invoices_api_model', 'invoices_api_model_v2024_06_19'],
      ['orders', 'orders_v2026_01_01'],
      ['sellers', 'sellers_v1'],
      ['shipping', 'shipping_v2'],
    ]);
  });
});
