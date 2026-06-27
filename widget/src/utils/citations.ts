/**
 * Citation URL derivation.
 *
 * The FastAPI contract returns ``slug`` + optional ``timestamp_seconds`` on
 * each citation (see api/orchestrator/contract.py::Citation). The widget
 * derives two outbound URLs from these:
 *
 *   - ``gktuition_url`` — the topic page on the live site:
 *       https://gktuition.ie/topic/<slug>/[?t=<seconds>]
 *     (URL convention observed at gktuition.ie/topic/the-line-4-area-of-triangle/)
 *
 *   - ``youtube_url`` — not derivable from the contract alone (the YouTube
 *     ID lives in the tutorial frontmatter, not on the citation). v1 deep-
 *     links to the gktuition.ie topic page where the YouTube player is
 *     embedded; the ``?t=<seconds>`` query string is honoured by both the
 *     WordPress page (it scrolls to the right anchor) and the embedded
 *     YouTube iframe (via timestamp). If/when the FastAPI contract grows a
 *     youtube_video_id field on Citation, swap the implementation here —
 *     widget consumers won't have to change.
 *
 * This is the contract-needs delta documented in CONTRACT_NEEDS.md.
 */

import type { Citation } from '../api/types';
import { CORPUS_TO_WP_SLUG } from './slugMap';

/**
 * Base origin for topic links. The widget is embedded inside the WordPress
 * site, so the topic pages live on the same origin — staging
 * (gktuitionstg.wpenginepowered.com) during testing, gktuition.ie in
 * production. Deriving from window.location.origin means the links are
 * correct in both places with no rebuild. Falls back to the production
 * origin in non-browser contexts (SSR / unit tests).
 */
function siteOrigin(): string {
  const origin =
    typeof window !== 'undefined' && window.location && window.location.origin
      ? window.location.origin
      : 'https://gktuition.ie';
  return origin.replace(/\/$/, '');
}

function topicBase(): string {
  return `${siteOrigin()}/topic`;
}

/**
 * Corpus docs that map to a LearnDash *strand* page (/lessons/<slug>/) rather
 * than an individual /topic/ lesson. The retrievable proof hubs are synthetic
 * docs with no /topic/ page of their own — their natural landing page is the
 * strand topic page that lists the proofs. Value is the full path from origin.
 */
const CORPUS_TO_WP_PATH: Record<string, string> = {
  'paper-1-proofs': '/lessons/proofs/',
  'paper-2-proofs': '/lessons/proofs-2/',
};

/**
 * Build the topic-page URL for a citation, or ``null`` when the cited corpus
 * slug has no WordPress equivalent (the caller renders plain text instead of
 * a dead link). The engine cites by descriptive corpus slugs; we translate to
 * the WordPress topic slug via the generated CORPUS_TO_WP_SLUG map.
 */
export function citationGktuitionUrl(citation: Citation): string | null {
  // Strand-level pages (e.g. the proof hubs) take precedence over /topic/.
  const strandPath = CORPUS_TO_WP_PATH[citation.slug];
  if (strandPath) return `${siteOrigin()}${strandPath}`;

  const wpSlug = CORPUS_TO_WP_SLUG[citation.slug];
  if (!wpSlug) return null;
  const base = `${topicBase()}/${encodeURIComponent(wpSlug)}/`;
  if (citation.timestamp_seconds != null && citation.timestamp_seconds > 0) {
    return `${base}?t=${citation.timestamp_seconds}`;
  }
  return base;
}

/**
 * Best-effort: links to the topic page (which embeds the YouTube player) with
 * the timestamp query honoured. v1 does not deep-link directly to youtube.com
 * because the citation does not carry the YouTube video ID — see file header.
 * Returns ``null`` when the slug has no WordPress page.
 */
export function citationYoutubeUrl(citation: Citation): string | null {
  return citationGktuitionUrl(citation);
}

export function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return '';
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }
  return `${m}:${String(sec).padStart(2, '0')}`;
}
