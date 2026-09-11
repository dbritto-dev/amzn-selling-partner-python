import { describe, expect, it } from 'vitest';
import { emit, TASKS_SPEC } from './helpers.js';

describe('generateClient: http_client.py and errors.py', () => {
  it('generates the retry and timeout policy from sdkBehavior', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['http_client.py'] ?? '';
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
