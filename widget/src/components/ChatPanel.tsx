import { useRef, useState, useEffect, type FormEvent } from 'react';
import type { ApiClient } from '../api/client';
import type { QueryClass, Tier, WidgetOptions } from '../api/types';
import { MessageBubble, type ChatMessage } from './MessageBubble';
import { EmailCaptureWall } from './EmailCaptureWall';

interface ChatPanelProps {
  position: NonNullable<WidgetOptions['position']>;
  client: ApiClient;
  tier: Tier;
  anonymousRateLimit: number;
  onClose: () => void;
}

const PROGRESS_TEXT: Record<QueryClass, string> = {
  concept: 'Explaining the concept…',
  solution_lookup: 'Looking up an exam solution…',
  summary_request: 'Pulling together the cram summary…',
  analytical: 'Counting it up across the corpus…',
  image_extracted: 'Reading the image and finding the question…',
  ambiguous: 'Searching across tutorials, solutions, and summaries…',
};

export function ChatPanel({
  position,
  client,
  tier,
  anonymousRateLimit,
  onClose,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<QueryClass | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wallShown, setWallShown] = useState(false);
  const [wallDismissed, setWallDismissed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Count of questions asked by an anonymous user (resets on tier upgrade).
  const anonymousAskedCount = messages.filter((m) => m.role === 'user').length;

  // Auto-scroll on new messages.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, progress]);

  // Cleanup any inflight request on unmount.
  useEffect(() => () => abortRef.current?.abort(), []);

  function shouldShowWall(): boolean {
    if (tier !== 'anonymous') return false;
    if (wallDismissed) return false;
    return anonymousAskedCount >= anonymousRateLimit;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q || busy) return;

    if (shouldShowWall()) {
      setWallShown(true);
      return;
    }

    setInput('');
    setError(null);

    const userMsg: ChatMessage = { id: makeId(), role: 'user', text: q };
    setMessages((prev) => [...prev, userMsg]);
    setBusy(true);
    setProgress('concept'); // generic initial guess; replaced by server response

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await client.postQuery({ q, debug: false }, ctrl.signal);
      setProgress(res.query_class);
      const assistantMsg: ChatMessage = {
        id: makeId(),
        role: 'assistant',
        text: res.answer,
        citations: res.citations,
        graphs: res.graphs,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setBusy(false);
      setProgress(null);
      abortRef.current = null;
    }
  }

  if (wallShown && !wallDismissed) {
    return (
      <div
        className={`gktuition-tutor__panel gktuition-tutor__panel--${position}`}
        role="dialog"
        aria-label="GKTuition AI tutor"
        data-testid="gktuition-panel"
      >
        <div className="gktuition-tutor__header">
          <h3>GKTuition AI Tutor</h3>
          <button
            type="button"
            className="gktuition-tutor__close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <EmailCaptureWall
          onSubmit={(_email) => {
            // v1: email is captured client-side. Server-side persistence is
            // a separate concern (Phase 2 — Mailchimp / Buttondown sink).
            setWallShown(false);
            setWallDismissed(true);
          }}
          onSkip={() => {
            setWallShown(false);
            setWallDismissed(true);
          }}
        />
      </div>
    );
  }

  return (
    <div
      className={`gktuition-tutor__panel gktuition-tutor__panel--${position}`}
      role="dialog"
      aria-label="GKTuition AI tutor"
      data-testid="gktuition-panel"
    >
      <div className="gktuition-tutor__header">
        <h3>GKTuition AI Tutor</h3>
        <button
          type="button"
          className="gktuition-tutor__close"
          onClick={onClose}
          aria-label="Close"
        >
          ×
        </button>
      </div>
      <div className="gktuition-tutor__messages" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="gktuition-tutor__bubble gktuition-tutor__bubble--assistant">
            Hi! Ask me anything about LCHL Maths — concepts, exam solutions, or revision summaries.
          </div>
        ) : null}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {busy && progress ? (
          <div className="gktuition-tutor__progress" data-testid="gktuition-progress">
            {PROGRESS_TEXT[progress]}
          </div>
        ) : null}
        {error ? (
          <div className="gktuition-tutor__error" data-testid="gktuition-error">
            {error}
          </div>
        ) : null}
      </div>
      <form className="gktuition-tutor__composer" onSubmit={handleSubmit}>
        <input
          className="gktuition-tutor__input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          aria-label="Question"
          disabled={busy}
          data-testid="gktuition-input"
        />
        <button
          type="submit"
          className="gktuition-tutor__send"
          disabled={busy || !input.trim()}
          data-testid="gktuition-send"
        >
          Send
        </button>
      </form>
    </div>
  );
}

function makeId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}
