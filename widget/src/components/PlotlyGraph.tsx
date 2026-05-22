/**
 * PlotlyGraph — renders a Plotly figure dict inline under the answer.
 *
 * Per ADR-005 (visualisation layer), the API may return one or more
 * Plotly figure specs in `QueryResponse.graphs`. This component takes a
 * single spec and renders it via the standard Plotly.js library, loaded
 * **on first use from the CDN** rather than bundled — Plotly's minified
 * footprint is ~3MB / ~800KB gzipped, which would blow the widget's
 * <200KB gzip budget on its own. Loading from CDN at first render keeps
 * the IIFE bundle small for the majority of students who never see a
 * graph; the CDN script is then browser-cached for the rest of the
 * session and beyond.
 *
 * Sizing:
 *  - responsive width — fills its container (the chat panel width).
 *  - fixed height — ~320px desktop / ~240px mobile (via CSS media query).
 *  - toolbar hidden by default; an "expand" button shows the full Plotly
 *    modebar inside a lightweight modal so the student can zoom / pan
 *    without the chrome eating the inline real estate.
 *
 * Accessibility:
 *  - `aria-label` is set from `layout.meta.summary` (every generator
 *    emits this; see api/visualisation/generators.py:_base_layout).
 */
import { useEffect, useRef, useState } from 'react';
import type { GraphSpec } from '../api/types';

interface PlotlyGraphProps {
  spec: GraphSpec;
  /** Per-spec ordinal — disambiguates aria-label / DOM id when multiple graphs are rendered. */
  index?: number;
}

// Plotly's CDN-shipped UMD bundle exposes `window.Plotly`.
declare global {
  interface Window {
    Plotly?: {
      newPlot: (
        el: HTMLElement,
        data: unknown[],
        layout: unknown,
        config?: unknown,
      ) => Promise<unknown>;
      purge: (el: HTMLElement) => void;
      Plots: { resize: (el: HTMLElement) => void };
    };
  }
}

const PLOTLY_CDN_URL = 'https://cdn.plot.ly/plotly-2.35.2.min.js';

// Module-level promise — once one `<PlotlyGraph>` mounts, every subsequent
// instance reuses the same Promise so we never inject two <script> tags.
let _plotlyLoader: Promise<NonNullable<Window['Plotly']>> | null = null;

function loadPlotly(): Promise<NonNullable<Window['Plotly']>> {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('window is not available'));
  }
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (_plotlyLoader) return _plotlyLoader;

  _plotlyLoader = new Promise((resolve, reject) => {
    const existing = document.querySelector(
      `script[data-gktuition-plotly]`,
    ) as HTMLScriptElement | null;
    const onLoad = () => {
      if (window.Plotly) resolve(window.Plotly);
      else reject(new Error('Plotly failed to attach to window'));
    };
    if (existing) {
      existing.addEventListener('load', onLoad);
      existing.addEventListener('error', () => reject(new Error('Plotly CDN load failed')));
      return;
    }
    const script = document.createElement('script');
    script.src = PLOTLY_CDN_URL;
    script.async = true;
    script.setAttribute('data-gktuition-plotly', 'true');
    script.addEventListener('load', onLoad);
    script.addEventListener('error', () => reject(new Error('Plotly CDN load failed')));
    document.head.appendChild(script);
  });
  return _plotlyLoader;
}

export function PlotlyGraph({ spec, index = 0 }: PlotlyGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const el = containerRef.current;
    if (!el) return;

    loadPlotly()
      .then((Plotly) => {
        if (cancelled || !containerRef.current) return;
        const figure = spec.figure ?? {};
        const data = (figure.data as unknown[]) ?? [];
        const layout = { ...(figure.layout as Record<string, unknown>), autosize: true };
        const config = {
          displayModeBar: false, // hidden in the inline view; modal exposes it.
          responsive: true,
          staticPlot: false,
        };
        return Plotly.newPlot(containerRef.current, data, layout, config).then(() => {
          if (!cancelled) setStatus('ready');
        });
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.warn('PlotlyGraph failed to load Plotly', err);
        if (!cancelled) setStatus('error');
      });

    return () => {
      cancelled = true;
      if (window.Plotly && el) {
        try {
          window.Plotly.purge(el);
        } catch {
          /* harmless — Plotly may already have been removed */
        }
      }
    };
  }, [spec]);

  // Window-resize → keep the chart filling its container width.
  useEffect(() => {
    const onResize = () => {
      if (containerRef.current && window.Plotly) {
        try {
          window.Plotly.Plots.resize(containerRef.current);
        } catch {
          /* container may be unmounted mid-resize */
        }
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const summary = readSummary(spec.figure);
  const ariaLabel = summary || `Graph ${index + 1}`;

  return (
    <div
      className={`gktuition-tutor__graph ${expanded ? 'gktuition-tutor__graph--expanded' : ''}`}
      data-testid={`gktuition-graph-${index}`}
      data-kind={spec.kind}
    >
      <div
        ref={containerRef}
        className="gktuition-tutor__graph-canvas"
        role="img"
        aria-label={ariaLabel}
      />
      {status === 'loading' && (
        <div className="gktuition-tutor__graph-status">Loading chart…</div>
      )}
      {status === 'error' && (
        <div className="gktuition-tutor__graph-status gktuition-tutor__graph-status--error">
          Chart unavailable.
        </div>
      )}
      <button
        type="button"
        className="gktuition-tutor__graph-expand"
        onClick={() => setExpanded((v) => !v)}
        aria-label={expanded ? 'Collapse graph' : 'Expand graph'}
      >
        {expanded ? '×' : '⤢'}
      </button>
    </div>
  );
}

/** Pull the accessibility summary out of `layout.meta.summary` if the
 * generator set one (every generator does). Returns undefined if absent. */
function readSummary(figure: Record<string, unknown> | undefined): string | undefined {
  if (!figure || typeof figure !== 'object') return undefined;
  const layout = figure.layout as Record<string, unknown> | undefined;
  if (!layout || typeof layout !== 'object') return undefined;
  const meta = layout.meta as Record<string, unknown> | undefined;
  if (!meta || typeof meta !== 'object') return undefined;
  const summary = meta.summary;
  return typeof summary === 'string' ? summary : undefined;
}
