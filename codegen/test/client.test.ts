import { describe, expect, it } from 'vitest';
import { compareVersions } from '../src/amazon.js';
import { generateClient, renderClientModule } from '../src/python/client.js';

describe('generateClient', () => {
  it('renders apis.py with one accessor per API version and the client classes', () => {
    const apis = generateClient({
      packageName: 'sdk',
      runtimePackage: 'amzn_selling_partner',
      entries: [
        { api: 'tasks', version: 'v1', title: 'Tasks API', operations: 5 },
        { api: 'tasks', version: 'v2', title: 'Tasks API', operations: 6 },
      ],
      aliases: { todo: 'tasks' },
      compareVersions,
    });
    expect(apis.path).toBe('apis.py');
    expect(apis.content).toContain('class TasksAPI(APIVersionsBase):');
    expect(apis.content).toContain('def v1(self) -> TasksV1:');
    expect(apis.content).toContain('def v2(self) -> TasksV2:');
    expect(apis.content).toContain('def latest(self) -> TasksV2:');
    expect(apis.content).toContain('class APIs(SyncAPIsBase):');
    expect(apis.content).toContain('class AsyncAPIs(AsyncAPIsBase):');
    expect(apis.content).toMatch(/def todo\(self\)/);
    const client = renderClientModule({ packageName: 'sdk', runtimePackage: 'amzn_selling_partner', clientName: 'TasksClient' });
    expect(client).toContain('class TasksClient(SyncAPIClient, APIs):');
    expect(client).toContain('class AsyncTasksClient(AsyncAPIClient, AsyncAPIs):');
    expect(client).toContain('_package = "sdk"');
  });
});
