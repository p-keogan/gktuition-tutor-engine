import type { Citation as CitationT, GraphSpec } from '../api/types';
import { Citation } from './Citation';
import { PlotlyGraph } from './PlotlyGraph';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  citations?: CitationT[];
  /** Plotly figure specs rendered inline under the answer (ADR-005). */
  graphs?: GraphSpec[];
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const cls =
    message.role === 'user'
      ? 'gktuition-tutor__bubble gktuition-tutor__bubble--user'
      : 'gktuition-tutor__bubble gktuition-tutor__bubble--assistant';
  return (
    <div className={cls} data-testid={`gktuition-msg-${message.role}`}>
      {message.text}
      {message.role === 'assistant' && message.graphs && message.graphs.length > 0 ? (
        <div className="gktuition-tutor__graphs">
          {message.graphs.map((g, i) => (
            <PlotlyGraph key={`graph-${i}-${g.kind}`} spec={g} index={i} />
          ))}
        </div>
      ) : null}
      {message.role === 'assistant' && message.citations && message.citations.length > 0 ? (
        <div className="gktuition-tutor__citations">
          {message.citations.map((c) => (
            <Citation key={c.slug + (c.timestamp_seconds ?? '')} citation={c} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
