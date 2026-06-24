/**
 * KaTeX math rendering for answer bubbles.
 *
 * The tutor's answers contain LaTeX between `\( … \)` (inline) and `\[ … \]`
 * (display) delimiters. Students never see raw LaTeX — we render it to real
 * formulas with KaTeX.
 *
 * KaTeX is BUNDLED into the widget (engine + auto-render JS, plus the layout
 * CSS with the woff2 fonts inlined as base64 in `../katex.css`). Earlier
 * attempts to load KaTeX from a CDN — both injected by the widget and enqueued
 * by WordPress — were blocked by the site's Content-Security-Policy, so the
 * formulas never rendered. Bundling removes every external dependency: there
 * is nothing left to block.
 */

import renderMathInElement from 'katex/contrib/auto-render';
import '../katex.css';

/** Bundled — always available. Kept async so callers don't need to change. */
export function ensureKatex(): Promise<void> {
  return Promise.resolve();
}

/** Render any LaTeX inside `el` in place. */
export function renderMath(el: HTMLElement): void {
  try {
    renderMathInElement(el, {
      // Order matters: multi-char delimiters first so "$$" is matched before
      // a single "$". The tutor emits a mix of \( \), \[ \], $$ $$ and $ $.
      delimiters: [
        { left: '\\[', right: '\\]', display: true },
        { left: '\\(', right: '\\)', display: false },
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false },
      ],
      throwOnError: false,
    });
  } catch {
    /* On any KaTeX error, leave the text as-is rather than breaking the answer. */
  }
}
