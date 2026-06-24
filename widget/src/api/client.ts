/**
 * Typed FastAPI client + WordPress tier-endpoint client.
 *
 * Auth contract: every call to the FastAPI side sends the JWT obtained from
 * the WordPress /wp-json/gktuition/v1/tier endpoint as `Authorization: Bearer`.
 * The JWT lives in memory (never localStorage) per ADR-002 redline note 3.
 */

import type {
  ImageQueryResult,
  QueryRequest,
  QueryResponse,
  TierResponse,
} from './types';

/**
 * The shape returned by ``createApiClient``. Each call attaches the current
 * JWT, refreshes it lazily if expired, and returns parsed JSON.
 */
export interface ApiClient {
  fetchTier(): Promise<TierResponse>;
  postQuery(req: QueryRequest, signal?: AbortSignal): Promise<QueryResponse>;
  /** Upload a photo of a question (+ optional caption) to /image_query (paying tier only). */
  postImageQuery(file: Blob, caption: string, signal?: AbortSignal): Promise<ImageQueryResult>;
  /** Test-only — get the current in-memory token. */
  _currentToken(): { jwt: string; exp: number; fastapiUrl: string } | null;
}

export interface ApiClientOptions {
  tierEndpoint: string;
  /** May be empty — falls back to TierResponse.fastapi_url. */
  fastapiUrl: string;
  /** WordPress REST nonce, sent as X-WP-Nonce so the tier endpoint sees the logged-in user. */
  restNonce?: string;
  /** Override for unit tests. Defaults to globalThis.fetch. */
  fetchImpl?: typeof fetch;
  /** Override for unit tests. Defaults to () => Date.now(). */
  now?: () => number;
}

export class ApiError extends Error {
  status: number;
  body: string;
  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

/**
 * Factory — closes over the in-memory token so it never escapes the
 * widget runtime. No module-level globals.
 */
export function createApiClient(opts: ApiClientOptions): ApiClient {
  const fetchImpl: typeof fetch = opts.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const now = opts.now ?? (() => Date.now());

  // Closed-over auth state. Lives only as long as the closure.
  let token: { jwt: string; exp: number; fastapiUrl: string } | null = null;
  let inflight: Promise<TierResponse> | null = null;

  async function fetchTier(): Promise<TierResponse> {
    // De-dupe simultaneous fetches.
    if (inflight) return inflight;
    inflight = (async () => {
      try {
        const headers: Record<string, string> = { Accept: 'application/json' };
        if (opts.restNonce) headers['X-WP-Nonce'] = opts.restNonce;
        const res = await fetchImpl(opts.tierEndpoint, {
          method: 'GET',
          credentials: 'same-origin',
          headers,
        });
        if (!res.ok) {
          const body = await safeText(res);
          throw new ApiError(`tier endpoint returned ${res.status}`, res.status, body);
        }
        const json = (await res.json()) as TierResponse;
        token = {
          jwt: json.jwt,
          exp: json.exp,
          fastapiUrl: json.fastapi_url || opts.fastapiUrl,
        };
        return json;
      } finally {
        inflight = null;
      }
    })();
    return inflight;
  }

  function isExpired(): boolean {
    if (!token) return true;
    // exp is in seconds (POSIX). Refresh 60s early.
    const nowSec = Math.floor(now() / 1000);
    return nowSec >= token.exp - 60;
  }

  async function ensureToken(): Promise<{ jwt: string; fastapiUrl: string }> {
    if (isExpired()) await fetchTier();
    if (!token) throw new ApiError('no token after fetch', 0, '');
    return { jwt: token.jwt, fastapiUrl: token.fastapiUrl };
  }

  async function postQuery(req: QueryRequest, signal?: AbortSignal): Promise<QueryResponse> {
    const auth = await ensureToken();
    const base = auth.fastapiUrl.replace(/\/$/, '');
    const res = await fetchImpl(`${base}/query`, {
      method: 'POST',
      signal,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Authorization: `Bearer ${auth.jwt}`,
      },
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      const body = await safeText(res);
      throw new ApiError(`/query returned ${res.status}`, res.status, body);
    }
    return (await res.json()) as QueryResponse;
  }

  async function postImageQuery(
    file: Blob,
    caption: string,
    signal?: AbortSignal,
  ): Promise<ImageQueryResult> {
    const auth = await ensureToken();
    const base = auth.fastapiUrl.replace(/\/$/, '');
    const fd = new FormData();
    // Field name must match the FastAPI param: image: UploadFile = File(...).
    fd.append('image', file, (file as File).name || 'question.jpg');
    if (caption && caption.trim()) fd.append('caption', caption.trim());
    const res = await fetchImpl(`${base}/image_query`, {
      method: 'POST',
      signal,
      // No Content-Type — the browser sets the multipart boundary itself.
      headers: { Accept: 'application/json', Authorization: `Bearer ${auth.jwt}` },
      body: fd,
    });
    if (!res.ok) {
      const body = await safeText(res);
      throw new ApiError(`/image_query returned ${res.status}`, res.status, body);
    }
    return (await res.json()) as ImageQueryResult;
  }

  return {
    fetchTier,
    postQuery,
    postImageQuery,
    _currentToken: () => token,
  };
}

async function safeText(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return '';
  }
}
