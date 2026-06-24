import type { Citation as CitationT } from '../api/types';
import { citationGktuitionUrl, formatTimestamp } from '../utils/citations';

interface CitationProps {
  citation: CitationT;
}

export function Citation({ citation }: CitationProps) {
  const url = citationGktuitionUrl(citation);
  const ts = formatTimestamp(citation.timestamp_seconds);
  const inner = (
    <>
      {citation.title}
      {ts ? <span className="gktuition-tutor__citation-time"> @ {ts}</span> : null}
    </>
  );
  // No WordPress page for this slug — render as plain (non-clickable) text so
  // we never emit a dead link.
  if (!url) {
    return (
      <span
        className="gktuition-tutor__citation gktuition-tutor__citation--nolink"
        data-testid="gktuition-citation"
        data-slug={citation.slug}
      >
        {inner}
      </span>
    );
  }
  return (
    <a
      className="gktuition-tutor__citation"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="gktuition-citation"
      data-slug={citation.slug}
    >
      {inner}
    </a>
  );
}
