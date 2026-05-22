import { describe, it, expect, vi } from 'vitest';
import { createApiClient } from '../src/api/client';
import { TIER_FIXTURE, QUERY_FIXTURES } from './fixtures';

function makeFetch(map: Record<string, unknown>): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    for (const [pattern, body] of Object.entries(map)) {
      if (url.includes(pattern)) {
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }
    return new Response('not found', { status: 404 });
  }) as unknown as typeof fetch;
}

describe('createApiClient', () => {
  it('fetches tier on fetchTier()', async () => {
    const client = createApiClient({
      tierEndpoint: '/wp-json/gktuition/v1/tier',
      fastapiUrl: 'http://fake-fastapi.test',
      fetchImpl: makeFetch({ '/tier': TIER_FIXTURE }),
    });
    const res = await client.fetchTier();
    expect(res.tier).toBe('anonymous');
    expect(res.jwt).toBe(TIER_FIXTURE.jwt);
  });

  it('attaches Bearer token to /query', async () => {
    const headers: Headers[] = [];
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (init?.headers) headers.push(new Headers(init.headers));
      if (url.includes('/tier')) {
        return new Response(JSON.stringify(TIER_FIXTURE), { status: 200 });
      }
      if (url.includes('/query')) {
        return new Response(JSON.stringify(QUERY_FIXTURES.concept), { status: 200 });
      }
      return new Response('nope', { status: 404 });
    }) as unknown as typeof fetch;

    const client = createApiClient({
      tierEndpoint: '/wp-json/gktuition/v1/tier',
      fastapiUrl: 'http://fake-fastapi.test',
      fetchImpl,
    });
    const res = await client.postQuery({ q: 'factorise diff of squares' });
    expect(res.query_class).toBe('concept');

    const queryHeaders = headers.find((h) => h.get('authorization'));
    expect(queryHeaders?.get('authorization')).toBe(`Bearer ${TIER_FIXTURE.jwt}`);
  });

  it('refreshes token when expired', async () => {
    let tierCalls = 0;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/tier')) {
        tierCalls += 1;
        return new Response(
          JSON.stringify({
            ...TIER_FIXTURE,
            // Already expired (tier endpoint always returns "now + 3600",
            // but we override here to simulate immediately-stale).
            exp: Math.floor(Date.now() / 1000) - 100,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify(QUERY_FIXTURES.concept), { status: 200 });
    }) as unknown as typeof fetch;

    const client = createApiClient({
      tierEndpoint: '/tier',
      fastapiUrl: 'http://fake.test',
      fetchImpl,
    });
    await client.fetchTier();
    await client.postQuery({ q: 'hi' }); // should trigger a refresh
    expect(tierCalls).toBeGreaterThanOrEqual(2);
  });

  it('throws ApiError on /query 500', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/tier')) {
        return new Response(JSON.stringify(TIER_FIXTURE), { status: 200 });
      }
      return new Response('oops', { status: 500 });
    }) as unknown as typeof fetch;

    const client = createApiClient({
      tierEndpoint: '/tier',
      fastapiUrl: 'http://fake.test',
      fetchImpl,
    });
    await expect(client.postQuery({ q: 'hi' })).rejects.toThrow(/500/);
  });
});
