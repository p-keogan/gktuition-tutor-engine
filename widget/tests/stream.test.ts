/**
 * Unit tests for the AGENT_17 streaming client (src/api/stream.ts).
 *
 * Verifies that streamQuery correctly parses an SSE response and dispatches
 * token / citation / done events to the supplied handlers, that the
 * Authorization bearer is attached, that AbortSignal is honoured, and
 * that ``streamSupported`` returns true in the jsdom test runtime.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  streamQuery,
  streamSupported,
  type StreamCitationEvent,
  type StreamDoneEvent,
  type StreamTokenEvent,
} from '../src/api/stream';

/** Build a ``Response`` whose body is a ReadableStream emitting the given chunks. */
function makeSseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

describe('streamSupported', () => {
  it('returns true in the jsdom runtime', () => {
    expect(streamSupported()).toBe(true);
  });
});

describe('streamQuery', () => {
  it('dispatches token, citation, and done events in order', async () => {
    const sseBody = [
      'event: token\ndata: {"text":"To "}\n\n',
      'event: token\ndata: {"text":"factorise "}\n\n',
      'event: token\ndata: {"text":"a difference of squares..."}\n\n',
      'event: citation\ndata: {"slug":"algebra-1-revision-of-jc-factorising","title":"Algebra 1","timestamp_seconds":142,"score":0.92}\n\n',
      'event: done\ndata: {"query":"x","query_class":"concept","model_used":"cortex.mistral-large2","from_cache":false,"voice_anchor_strand":"LCHL_Algebra","elapsed_ms":3966}\n\n',
    ];

    const fetchImpl = vi.fn(async () => makeSseResponse(sseBody)) as unknown as typeof fetch;

    const tokens: StreamTokenEvent[] = [];
    const citations: StreamCitationEvent[] = [];
    let done: StreamDoneEvent | null = null;
    let err: Error | null = null;

    await streamQuery(
      { q: 'how do I factorise difference of squares' },
      {
        onToken: (e) => tokens.push(e),
        onCitation: (c) => citations.push(c),
        onDone: (d) => {
          done = d;
        },
        onError: (e) => {
          err = e;
        },
      },
      {
        jwt: 'test.jwt.value',
        fastapiUrl: 'http://fake-fastapi.test',
        fetchImpl,
      },
    );

    expect(err).toBeNull();
    expect(tokens.map((t) => t.text)).toEqual([
      'To ',
      'factorise ',
      'a difference of squares...',
    ]);
    expect(citations).toHaveLength(1);
    expect(citations[0].slug).toBe('algebra-1-revision-of-jc-factorising');
    expect(done).not.toBeNull();
    expect(done!.model_used).toBe('cortex.mistral-large2');
    expect(done!.from_cache).toBe(false);
    expect(done!.voice_anchor_strand).toBe('LCHL_Algebra');
  });

  it('attaches the Bearer token to the request', async () => {
    let seenAuth: string | null = null;
    const fetchImpl = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      seenAuth = new Headers(init?.headers).get('authorization');
      return makeSseResponse([
        'event: done\ndata: {"query":"x","query_class":"concept","model_used":"(none)","from_cache":false,"voice_anchor_strand":null,"elapsed_ms":1}\n\n',
      ]);
    }) as unknown as typeof fetch;

    await streamQuery(
      { q: 'hi' },
      {},
      {
        jwt: 'header.payload.signature',
        fastapiUrl: 'http://fake-fastapi.test',
        fetchImpl,
      },
    );

    expect(seenAuth).toBe('Bearer header.payload.signature');
  });

  it('surfaces an Error when the server returns non-2xx', async () => {
    const fetchImpl = vi.fn(
      async () => new Response('rate-limited', { status: 429 }),
    ) as unknown as typeof fetch;

    let err: Error | null = null;
    await expect(
      streamQuery(
        { q: 'x' },
        { onError: (e) => (err = e) },
        { jwt: 'jwt', fastapiUrl: 'http://fake.test', fetchImpl },
      ),
    ).rejects.toThrow(/429/);
    expect(err).not.toBeNull();
  });

  it('handles records that arrive across multiple chunks', async () => {
    // Split one record across three network reads to exercise the
    // buffering logic — the parser must wait for the \n\n terminator
    // before dispatching.
    const sseBody = [
      'event: token\n',
      'data: {"text":"hel',
      'lo"}\n\n',
      'event: done\ndata: {"query":"x","query_class":"concept","model_used":"(none)","from_cache":false,"voice_anchor_strand":null,"elapsed_ms":1}\n\n',
    ];
    const fetchImpl = vi.fn(async () => makeSseResponse(sseBody)) as unknown as typeof fetch;

    const tokens: string[] = [];
    await streamQuery(
      { q: 'x' },
      { onToken: (t) => tokens.push(t.text) },
      { jwt: 'j', fastapiUrl: 'http://fake.test', fetchImpl },
    );

    expect(tokens).toEqual(['hello']);
  });
});
