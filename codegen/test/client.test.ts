import { describe, expect, it } from 'vitest';
import { latestAliases } from '../src/python/client.js';
import { emit, TASKS_SPEC } from './helpers.js';

describe('generateClient', () => {
  it('renders the namespace class and its async twin with one lazy resource per service', async () => {
    const files = await emit(TASKS_SPEC, 'TasksClient');
    const content = files['client.py'] ?? '';
    expect(content).toContain('class TasksClient:');
    expect(content).toContain('class AsyncTasksClient:');
    expect(content).toContain('base_url: str = "https://api.tasks.example.com",');
    expect(content).toContain('self._http = HttpClient(');
    expect(content).toContain('self._http = AsyncHttpClient(');
    expect(content).toContain('    @cached_property\n    def tasks(self) -> TasksResource:\n        from .resources.tasks import TasksResource\n\n        return TasksResource(self._http)');
    expect(content).toContain('    def with_options(self, **options: Any) -> Self:');
    expect(content).toContain('_RESOURCES = ("tasks",)');
    expect(content).toContain('__all__ = ["AsyncTasksClient", "TasksClient"]');
  });

  it('exports the clients, errors and request options from __init__.py', async () => {
    const files = await emit(TASKS_SPEC, 'TasksClient');
    const init = files['__init__.py'] ?? '';
    expect(init).toContain('from .client import AsyncTasksClient, TasksClient');
    expect(init).toContain('from ._http import RateLimit, RequestContext, RequestOptions');
    expect(init).toContain('NotFoundError');
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

describe('generateErrors: errors.py and _http.py', () => {
  it('generates the retry and timeout policy from the SDK behavior, not hardcoded', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['_http.py'] ?? '';
    // oagen defaults merged with emitterOptions.python.sdkBehavior in oagen.config.ts
    expect(content).toContain('RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})');
    expect(content).toContain('MAX_RETRIES = 2');
    expect(content).toContain('INITIAL_DELAY = 0.5');
    expect(content).toContain('MAX_DELAY = 8');
    expect(content).toContain('DEFAULT_TIMEOUT = float(os.environ.get("AMZN_SELLING_PARTNER_TIMEOUT", 30))');
    expect(content).toContain('REQUEST_ID_HEADER = "x-amzn-RequestId"');
    expect(content).toContain('class HttpClient(_BaseHttpClient):');
    expect(content).toContain('class AsyncHttpClient(_BaseHttpClient):');
    expect(content).toContain('def paginate(');
    expect(content).toContain('def with_options(self, **overrides: Any) -> Self:');
  });

  it('generates the error hierarchy from the error policy', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['errors.py'] ?? '';
    for (const cls of ['BadRequestError', 'AuthenticationError', 'AuthorizationError', 'NotFoundError', 'ConflictError', 'UnprocessableEntityError', 'RateLimitExceededError', 'ServerError']) {
      expect(content).toContain(`class ${cls}(APIStatusError):`);
    }
    expect(content).toContain('    429: RateLimitExceededError,');
    expect(content).toContain('def status_error_class(status_code: int) -> type[APIStatusError]:');
  });
});
