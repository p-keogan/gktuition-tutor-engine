import { useRef, useState, useEffect, type ChangeEvent, type FormEvent } from 'react';
import type { ApiClient } from '../api/client';
import { streamQuery, streamSupported } from '../api/stream';
import type { Citation, ExamAppearance, QueryClass, Tier, WidgetOptions } from '../api/types';
import { MessageBubble, type ChatMessage } from './MessageBubble';
import { EmailCaptureWall } from './EmailCaptureWall';

interface ChatPanelProps {
  position: NonNullable<WidgetOptions['position']>;
  client: ApiClient;
  tier: Tier;
  anonymousRateLimit: number;
  onClose: () => void;
  /**
   * Force the non-streaming JSON path even when ``streamSupported()`` is
   * true. Defaults to false. Exposed for tests + as an emergency kill
   * switch for the streaming code path.
   */
  disableStreaming?: boolean;
}

const PROGRESS_TEXT: Record<QueryClass, string> = {
  concept: 'Explaining the concept…',
  solution_lookup: 'Looking up an exam solution…',
  summary_request: 'Pulling together the cram summary…',
  analytical: 'Counting it up across the corpus…',
  image_extracted: 'Reading the image and finding the question…',
  ambiguous: 'Searching across tutorials, solutions, and summaries…',
};

/**
 * Generic pre-first-token thinking indicator (AGENT_17). Shown between
 * "user pressed Send" and "first ``token`` event arrives". Once tokens
 * start flowing the indicator disappears — the in-progress assistant
 * bubble takes over.
 */
const LOOKING_UP_TEXT = 'Looking up answer…';

export function ChatPanel({
  position,
  client,
  tier,
  anonymousRateLimit,
  onClose,
  disableStreaming = false,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<QueryClass | null>(null);
  /**
   * AGENT_17: shown between "user submitted" and "first token arrived"
   * on the streaming path. Replaced by the in-progress assistant bubble
   * as soon as a token lands. Independent of ``progress`` so the
   * non-streaming path keeps its query-class-aware indicator.
   */
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wallShown, setWallShown] = useState(false);
  const [wallDismissed, setWallDismissed] = useState(false);
  // Larger panel toggle — students on bigger screens can expand the window.
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Count of questions asked by an anonymous user (resets on tier upgrade).
  const anonymousAskedCount = messages.filter((m) => m.role === 'user').length;

  // Auto-scroll on new messages.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, progress, thinking]);

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

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    // AGENT_17: prefer the streaming path when the runtime supports it
    // and it hasn't been disabled. Fall back to the non-streaming JSON
    // path on any error mid-stream.
    const useStream = !disableStreaming && streamSupported();

    if (useStream) {
      setThinking(true);
      setProgress(null);
      const ok = await runStreamingQuery(q, ctrl);
      if (ok) {
        setBusy(false);
        setThinking(false);
        abortRef.current = null;
        return;
      }
      // Streaming failed — fall through to the JSON path. The error
      // surfaces only if the JSON path also fails.
      setThinking(false);
    }

    setProgress('concept'); // generic initial guess; replaced by server response
    try {
      const res = await client.postQuery({ q, debug: false }, ctrl.signal);
      setProgress(res.query_class);
      const assistantMsg: ChatMessage = {
        id: makeId(),
        role: 'assistant',
        text: res.answer,
        citations: res.citations,
        graphs: res.graphs,
        examAppearances: res.exam_appearances,
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

  async function handleImageSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Reset the input so selecting the same file again re-fires change.
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (!file || busy) return;

    setError(null);
    setMessages((prev) => [
      ...prev,
      { id: makeId(), role: 'user', text: `📷 Uploaded a photo: ${file.name}` },
    ]);
    setBusy(true);
    setThinking(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await client.postImageQuery(file, ctrl.signal);
      if (res.questions && res.questions.length > 0) {
        const list = res.questions.map((q, i) => `${i + 1}. ${q}`).join('\n');
        setMessages((prev) => [
          ...prev,
          {
            id: makeId(),
            role: 'assistant',
            text:
              'I spotted more than one question in that image. Type the one you want help with:\n\n' +
              list,
          },
        ]);
      } else if (res.rag_response) {
        const r = res.rag_response;
        const prefix = res.extracted_question
          ? `Question I read: "${res.extracted_question}"\n\n`
          : '';
        setMessages((prev) => [
          ...prev,
          {
            id: makeId(),
            role: 'assistant',
            text: prefix + r.answer,
            citations: r.citations,
            graphs: r.graphs,
            examAppearances: r.exam_appearances,
          },
        ]);
      } else {
        setError("I couldn't read a question from that image. Try a clearer, closer photo.");
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : String(err);
      if (/40[13]/.test(msg)) {
        setError('Photo questions are available on the paid plan.');
      } else if (/422/.test(msg)) {
        setError(
          "I couldn't find a clear maths question in that photo. Make sure the " +
            'question is fully in frame and well-lit, then try again.',
        );
      } else if (/50[0-9]/.test(msg)) {
        setError('I had trouble reading that image — please retake the photo and try again.');
      } else {
        setError(msg);
      }
    } finally {
      setBusy(false);
      setThinking(false);
      abortRef.current = null;
    }
  }

  /**
   * AGENT_17 streaming-path handler.
   *
   * Returns true on a clean stream (``done`` event seen), false on any
   * error before ``done`` — the caller then falls back to the JSON path.
   * Mid-stream tokens append to a draft assistant message in-place.
   */
  async function runStreamingQuery(q: string, ctrl: AbortController): Promise<boolean> {
    // We need the current JWT + fastapiUrl from the api client. The
    // ``_currentToken`` accessor is documented as test-only but it's
    // also the cleanest way to share the in-memory token with the
    // streaming path without redesigning the client surface in this
    // dispatch. AGENT_17 follow-up: promote it to a first-class method.
    const tok = client._currentToken();
    if (!tok) {
      // No cached token — fetch one via the existing JSON-path
      // ``postQuery`` plumbing by triggering ``fetchTier``. Easiest
      // way to do this without touching the client surface is to fall
      // back; the JSON path will fetch + populate the token.
      return false;
    }

    const draftId = makeId();
    let buffer = '';
    let citations: Citation[] = [];
    let examAppearances: ExamAppearance[] = [];
    let firstTokenSeen = false;
    let done = false;

    function flushDraft() {
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === draftId);
        if (idx === -1) {
          return [
            ...prev,
            {
              id: draftId,
              role: 'assistant',
              text: buffer,
              citations: citations.length ? citations : undefined,
              examAppearances: examAppearances.length ? examAppearances : undefined,
            },
          ];
        }
        const next = prev.slice();
        next[idx] = {
          ...next[idx],
          text: buffer,
          citations: citations.length ? citations : next[idx].citations,
          examAppearances: examAppearances.length
            ? examAppearances
            : next[idx].examAppearances,
        };
        return next;
      });
    }

    try {
      await streamQuery(
        { q, debug: false },
        {
          onToken: (ev) => {
            if (!firstTokenSeen) {
              firstTokenSeen = true;
              setThinking(false);
            }
            buffer += ev.text;
            flushDraft();
          },
          onCitation: (c) => {
            citations.push(c);
            flushDraft();
          },
          onDone: (ev) => {
            done = true;
            if (ev.exam_appearances && ev.exam_appearances.length) {
              examAppearances = ev.exam_appearances;
              flushDraft();
            }
          },
        },
        {
          jwt: tok.jwt,
          fastapiUrl: tok.fastapiUrl,
          signal: ctrl.signal,
        },
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        // User cancelled; don't fall back, don't surface an error.
        return true;
      }
      if (!firstTokenSeen) {
        // No tokens ever arrived → silent fall-through to JSON path.
        return false;
      }
      // Partial answer was delivered; surface the error and keep what
      // we got rather than re-running the query.
      setError(err instanceof Error ? err.message : String(err));
      return true;
    }

    if (!done) {
      // Stream closed without ``done`` — could be a proxy timing out
      // mid-stream. If we never got a token at all, fall back; if we
      // got some text, keep it and surface a soft warning via error.
      if (!firstTokenSeen) return false;
      setError('Stream closed before completion.');
    }
    return true;
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
      className={`gktuition-tutor__panel gktuition-tutor__panel--${position}${
        expanded ? ' gktuition-tutor__panel--expanded' : ''
      }`}
      role="dialog"
      aria-label="GKTuition AI tutor"
      data-testid="gktuition-panel"
    >
      <div className="gktuition-tutor__header">
        <h3>GKTuition AI Tutor</h3>
        <div className="gktuition-tutor__header-actions">
          <button
            type="button"
            className="gktuition-tutor__expand"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? 'Shrink window' : 'Enlarge window'}
            title={expanded ? 'Shrink' : 'Enlarge'}
          >
            {expanded ? '🗗' : '⤢'}
          </button>
          <button
            type="button"
            className="gktuition-tutor__close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>
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
        {busy && thinking ? (
          <div className="gktuition-tutor__progress" data-testid="gktuition-thinking">
            {LOOKING_UP_TEXT}
          </div>
        ) : null}
        {busy && !thinking && progress ? (
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
        {tier === 'paying' ? (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleImageSelected}
              style={{ display: 'none' }}
              data-testid="gktuition-image-input"
            />
            <button
              type="button"
              className="gktuition-tutor__attach"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              aria-label="Upload a photo of a question"
              title="Upload a photo of a question"
            >
              📷
            </button>
          </>
        ) : null}
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
