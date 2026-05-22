/**
 * TypeScript mirror of api/orchestrator/contract.py.
 *
 * Single source of truth on the wire is the Pydantic contract; this file
 * exists so the widget gets compile-time type-safety against the same shape.
 * Keep these in lockstep — if the Python contract changes, update this file.
 */

export type Tier = 'anonymous' | 'authenticated_free' | 'paying';

export type QueryClass =
  | 'concept'
  | 'solution_lookup'
  | 'summary_request'
  | 'analytical'
  | 'image_extracted'
  | 'ambiguous';

export interface Citation {
  slug: string;
  title: string;
  /** Seconds offset into source video; null/undefined for non-video sources. */
  timestamp_seconds?: number | null;
  /** Reranker confidence, 0..1. */
  score: number;
}

export interface RetrievedChunk {
  slug: string;
  snippet: string;
  score: number;
}

export interface ExamAppearance {
  year: number;
  paper: number;
  question: string;
  level: string;
  marks: number;
  note?: string | null;
}

export interface LearningWorkEntry {
  topic: string;
  tutorial_slug: string;
  note?: string | null;
}

/**
 * One Plotly figure attached to an answer. The widget passes `figure` to
 * `Plotly.newPlot` verbatim — see ADR-005 (visualisation layer) and
 * `api/visualisation/generators.py`. `kind` identifies which generator
 * produced this figure and is used by the eval harness + widget analytics.
 */
export interface GraphSpec {
  kind:
    | 'polynomial'
    | 'trig'
    | 'exponential'
    | 'log'
    | 'piecewise'
    | 'data_points'
    | 'overlay';
  figure: Record<string, unknown>;
}

export interface QueryRequest {
  q: string;
  /** Ignored by the server — the JWT-decoded tier is authoritative. */
  tier?: Tier;
  debug?: boolean;
}

export interface QueryResponse {
  query: string;
  answer: string;
  query_class: QueryClass;
  citations: Citation[];
  retrieved: RetrievedChunk[];
  exam_appearances: ExamAppearance[];
  related_learning_work: LearningWorkEntry[];
  /** Plotly figure specs rendered inline under the answer text (ADR-005). */
  graphs?: GraphSpec[];
  /**
   * One of 'cortex.mistral-large2' | 'anthropic.claude-haiku-4-5' |
   * 'anthropic.claude-sonnet-4' | 'cortex.analyst' | '(none)'.
   */
  model_used: string;
  from_cache: boolean;
  elapsed_ms: number;
  debug_info?: Record<string, unknown> | null;
}

/** Response from GET /wp-json/gktuition/v1/tier — see Stack A. */
export interface TierResponse {
  tier: Tier;
  jwt: string;
  exp: number;
  fastapi_url: string;
}

export interface WidgetOptions {
  /** Absolute URL of the WP REST endpoint that returns tier + JWT. */
  tierEndpoint?: string;
  /** Absolute base URL of the FastAPI orchestrator. Falls back to TierResponse.fastapi_url. */
  fastapiUrl?: string;
  /** Floating-button placement. */
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  /**
   * Anonymous-tier soft-wall threshold. When an anonymous user has asked
   * `anonymousRateLimit` questions, the email-capture wall is rendered.
   * Default 3. (Server-side rate limiting is independent; this is UX.)
   */
  anonymousRateLimit?: number;
}
