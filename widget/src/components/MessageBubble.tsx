import { useEffect, useRef } from 'react';
import type { Citation as CitationT, ExamAppearance, GraphSpec } from '../api/types';
import { Citation } from './Citation';
import { PlotlyGraph } from './PlotlyGraph';
import { ensureKatex, renderMath } from '../utils/katex';
import { renderAnswer } from '../utils/richtext';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  citations?: CitationT[];
  /** Curated exam appearances for the cited tutorials. */
  examAppearances?: ExamAppearance[];
  /** Plotly figure specs rendered inline under the answer (ADR-005). */
  graphs?: GraphSpec[];
}

/** Two most recent exam appearances, newest first, de-duplicated by year+paper+question. */
function recentExamAppearances(items: ExamAppearance[]): ExamAppearance[] {
  const seen = new Set<string>();
  return [...items]
    .sort((a, b) => b.year - a.year || b.paper - a.paper)
    .filter((e) => {
      const key = `${e.year}-${e.paper}-${e.question}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 2);
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isAssistant = message.role === 'assistant';
  const cls = isAssistant
    ? 'gktuition-tutor__bubble gktuition-tutor__bubble--assistant'
    : 'gktuition-tutor__bubble gktuition-tutor__bubble--user';

  // Assistant answers contain LaTeX (\( … \) and \[ … \]). We set the text
  // imperatively and render it through KaTeX, rather than via JSX, so React
  // doesn't fight KaTeX over the DOM it rewrites. Re-runs as tokens stream in;
  // incomplete delimiters are simply left untouched until their pair arrives.
  const answerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = answerRef.current;
    if (!el || !isAssistant) return;
    // Render the small Markdown subset (lists / bold / paragraphs) into real
    // DOM, then let KaTeX typeset any LaTeX in the resulting text nodes.
    renderAnswer(el, message.text);
    ensureKatex()
      .then(() => {
        if (answerRef.current) renderMath(answerRef.current);
      })
      .catch(() => {
        /* KaTeX CDN unavailable — answer still readable as plain text. */
      });
  }, [message.text, isAssistant]);

  return (
    <div className={cls} data-testid={`gktuition-msg-${message.role}`}>
      {isAssistant ? (
        <div ref={answerRef} className="gktuition-tutor__answer" />
      ) : (
        message.text
      )}
      {message.role === 'assistant' && message.graphs && message.graphs.length > 0 ? (
        <div className="gktuition-tutor__graphs">
          {message.graphs.map((g, i) => (
            <PlotlyGraph key={`graph-${i}-${g.kind}`} spec={g} index={i} />
          ))}
        </div>
      ) : null}
      {message.role === 'assistant' && message.citations && message.citations.length > 0 ? (
        <div className="gktuition-tutor__citations">
          {/* Show the two strongest tutorials only — five was too much. */}
          {message.citations.slice(0, 2).map((c) => (
            <Citation key={c.slug + (c.timestamp_seconds ?? '')} citation={c} />
          ))}
        </div>
      ) : null}
      {message.role === 'assistant' &&
      message.examAppearances &&
      message.examAppearances.length > 0 ? (
        <div className="gktuition-tutor__exams">
          <span className="gktuition-tutor__exams-label">Seen in exams:</span>{' '}
          {recentExamAppearances(message.examAppearances).map((e, i) => (
            <span key={`${e.year}-${e.paper}-${e.question}`} className="gktuition-tutor__exam">
              {i > 0 ? ', ' : ''}
              {e.year} Paper&nbsp;{e.paper} {e.question}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
