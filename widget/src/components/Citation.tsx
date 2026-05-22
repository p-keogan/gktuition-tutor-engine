import type { Citation as CitationT } from '../api/types';
import { citationGktuitionUrl, formatTimestamp } from '../utils/citations';

interface CitationProps {
  citation: CitationT;
}

export function Citation({ citation }: CitationProps) {
  const url = citationGktuitionUrl(citation);
  const ts = formatTimestamp(citation.timestamp_seconds);
  return (
    <a
      className="gktuition-tutor__citation"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="gktuition-citation"
      data-slug={citation.slug}
    >
      {citation.title}
      {ts ? <span className="gktuition-tutor__citation-time"> @ {ts}</span> : null}
    </a>
  );
}
