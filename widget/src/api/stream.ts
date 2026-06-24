/**
 * Streaming client for ``POST /query/stream`` — AGENT_17.
 *
 * Why ``fetch`` + ``ReadableStream`` and not ``EventSource``?
 * The browser-native ``EventSource`` is GET-only and provides no way to
 * attach a request body or an ``Authorization`` header. The widely-used
 * pattern for authenticated POST-streamed SSE is to call ``fetch()`` with
 * the JSON body and ``Bearer`` token, then iterate ``response.body`` as
 * a ``ReadableStream`` and parse the SSE record framing ourselves. The
 * parsing is small enough (~20 lines) that the dependency-free version
 * is worth it.
 *
 * Callers receive granular events via the ``handlers`` object — one
 * callback per event type plus an ``onError`` for transport failures. The
 * widget wires these to React state setters so the UI updates
 * progressively as tokens arrive.
 *
 * Fallback strategy (per the AGENT_17 dispatch): the caller should
 * detect ``streamSupported()`` returning false (or any ``onError``
 * firing before ``onDone``) and fall back to the non-streaming JSON
 * ``postQuery`` path.
 */

import type { Citation, ExamAppearance, GraphSpec, QueryClass, QueryRequest } from './types';

/** Payload of ``event: token`` per ``contract.py::StreamTokenData``. */
export interface StreamTokenEvent {
  text: string;
}

/** Payload of ``event: citation`` per ``contract.py::StreamCitationData``. */
export type StreamCitationEvent = Citation;

/** Payload of ``event: done`` per ``contract.py::StreamDoneData``. */
export interface StreamDoneEvent {
  query: string;
  query_class: QueryClass;
  model_used: string;
  from_cache: boolean;
  voice_anchor_strand: string | null;
  elapsed_ms: number;
  exam_appearances?: ExamAppearance[];
}

export interface StreamHandlers {
  onToken?(ev: StreamTokenEvent): void;
  onCitation?(ev: StreamCitationEvent): void;
  onGraph?(ev: GraphSpec): void;
  onDone?(ev: StreamDoneEvent): void;
  onError?(err: Error): void;
}

export interface StreamQueryOptions {
  /** The widget client's currently-valid JWT. */
  jwt: string;
  /** Absolute base URL of the FastAPI orchestrator (no trailing slash). */
  fastapiUrl: string;
  /** Cancel the in-flight request. */
  signal?: AbortSignal;
  /** Overridable for unit tests. Defaults to ``globalThis.fetch``. */
  fetchImpl?: typeof fetch;
}

/**
 * Detect whether the runtime can consume an SSE stream from a POST.
 *
 * Requires ``ReadableStream`` (for streamed response bodies) and
 * ``TextDecoder`` (for decoding chunks). Both are present in every
 * evergreen browser circa 2026 and in Node 18+, but old WebViews on
 * older Android handsets sometimes lack them; the widget falls back to
 * the non-streaming JSON path when this returns false.
 */
export function streamSupported(): boolean {
  return (
    typeof ReadableStream !== 'undefined' &&
    typeof TextDecoder !== 'undefined' &&
    typeof globalThis.fetch === 'function'
  );
}

/**
 * Consume a ``POST /query/stream`` SSE response, invoking handlers per event.
 *
 * Resolves when the server-side stream closes cleanly (``done`` event seen
 * AND the underlying ReadableStream ends). Rejects on transport failure or
 * on a non-200 response; in either case ``onError`` is invoked first if
 * provided. Cancellation via ``signal`` aborts the underlying fetch.
 */
export async function streamQuery(
  req: QueryRequest,
  handlers: StreamHandlers,
  opts: StreamQueryOptions,
): Promise<void> {
  const fetchImpl: typeof fetch = opts.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const base = opts.fastapiUrl.replace(/\/$/, '');

  let res: Response;
  try {
    res = await fetchImpl(`${base}/query/stream`, {
      method: 'POST',
      signal: opts.signal,
      headers: {
        'Content-Type': 'application/json',
        // Accept the SSE media type — informational; the server returns
        // ``text/event-stream`` regardless, but listing it makes the
        // intent obvious to any inspecting proxy.
        Accept: 'text/event-stream',
        Authorization: `Bearer ${opts.jwt}`,
      },
      body: JSON.stringify(req),
    });
  } catch (err) {
    const e = err instanceof Error ? err : new Error(String(err));
    handlers.onError?.(e);
    throw e;
  }

  if (!res.ok || !res.body) {
    const body = await safeText(res);
    const e = new Error(`/query/stream returned ${res.status}: ${body}`);
    handlers.onError?.(e);
    throw e;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  // SSE records are separated by a blank line (\n\n). We buffer raw
  // bytes-decoded-to-string until we see the separator, then dispatch
  // each complete record. Carry the trailing partial across reads.
  let buf = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // Normalise CRLF → LF so the splitter below is single-char.
      buf = buf.replace(/\r\n/g, '\n');
      let sepIdx: number;
      while ((sepIdx = buf.indexOf('\n\n')) !== -1) {
        const record = buf.slice(0, sepIdx);
        buf = buf.slice(sepIdx + 2);
        dispatchRecord(record, handlers);
      }
    }
    // Flush any trailing partial record (servers should always end with
    // a blank line, but be defensive).
    if (buf.trim()) {
      dispatchRecord(buf, handlers);
    }
  } catch (err) {
    const e = err instanceof Error ? err : new Error(String(err));
    handlers.onError?.(e);
    throw e;
  }
}

function dispatchRecord(record: string, handlers: StreamHandlers): void {
  // An SSE record is N lines of ``field: value`` (or comments starting
  // with ``:``). We only care about ``event`` and ``data``. Multi-line
  // ``data`` should be joined with ``\n``; in practice our server always
  // emits a single ``data:`` line per record because JSON is one line.
  let eventName = 'message';
  const dataLines: string[] = [];
  for (const rawLine of record.split('\n')) {
    if (!rawLine || rawLine.startsWith(':')) continue;
    const colonIdx = rawLine.indexOf(':');
    if (colonIdx === -1) continue;
    const field = rawLine.slice(0, colonIdx);
    // Per SSE spec: if the value starts with a single space, strip it.
    let value = rawLine.slice(colonIdx + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') eventName = value;
    else if (field === 'data') dataLines.push(value);
  }
  if (dataLines.length === 0) return;
  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join('\n'));
  } catch {
    // Bad JSON — surface as an error and skip rather than crash the stream.
    handlers.onError?.(new Error(`malformed SSE data: ${dataLines.join('\n')}`));
    return;
  }
  switch (eventName) {
    case 'token':
      handlers.onToken?.(payload as StreamTokenEvent);
      return;
    case 'citation':
      handlers.onCitation?.(payload as StreamCitationEvent);
      return;
    case 'graph':
      handlers.onGraph?.(payload as GraphSpec);
      return;
    case 'done':
      handlers.onDone?.(payload as StreamDoneEvent);
      return;
    default:
      // Unknown event types are ignored per SSE spec.
      return;
  }
}

async function safeText(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return '';
  }
}
