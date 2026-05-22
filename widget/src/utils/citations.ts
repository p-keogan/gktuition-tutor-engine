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

const TOPIC_BASE = 'https://gktuition.ie/topic';

export function citationGktuitionUrl(citation: Citation): string {
  const slug = encodeURIComponent(citation.slug);
  const base = `${TOPIC_BASE}/${slug}/`;
  if (citation.timestamp_seconds != null && citation.timestamp_seconds > 0) {
    return `${base}?t=${citation.timestamp_seconds}`;
  }
  return base;
}

/**
 * Best-effort: links to the gktuition.ie topic page (which embeds the
 * YouTube player) with the timestamp query honoured. v1 does not deep-link
 * directly to youtube.com because the citation does not carry the YouTube
 * video ID — see file header.
 */
export function citationYoutubeUrl(citation: Citation): string {
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
