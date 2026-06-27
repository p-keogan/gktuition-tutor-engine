/**
 * Minimal, safe Markdown-ish renderer for tutor answer bubbles.
 *
 * The answer bubble used to set `el.textContent = answer`, which meant any
 * Markdown the model emitted (bullet lists, **bold**) showed as literal `-` and
 * `**` characters. This renderer turns a small, well-defined subset of Markdown
 * into real DOM so enumerated answers (types of factorising, exam steps, …)
 * read as proper bullet lists.
 *
 * Supported:
 *   - unordered lists:  lines starting with `-`, `*` or `•`
 *   - ordered lists:    lines starting with `1.` / `1)`
 *   - paragraphs:       runs of non-list lines, split on blank lines
 *   - inline bold:      **like this**
 *
 * Everything else is left as plain text. Crucially, math delimiters (`$…$`,
 * `\(…\)`, `\[…\]`, `$$…$$`) are NOT touched here — we build text nodes and let
 * KaTeX's `renderMath` walk them afterwards, exactly as before.
 *
 * Security: we never assign the raw answer to `innerHTML`. The only elements we
 * create are `<p>`, `<ul>`, `<ol>`, `<li>`, `<strong>`; all answer text goes in
 * via `textContent` / `createTextNode`, so the model cannot inject markup.
 */

const UL_RE = /^\s*[-*•]\s+(.*)$/;
const OL_RE = /^\s*\d+[.)]\s+(.*)$/;
const BOLD_SPLIT_RE = /(\*\*[^*]+\*\*)/g;
const BOLD_MATCH_RE = /^\*\*([^*]+)\*\*$/;

/** Append `text` to `parent`, turning **bold** into <strong>; rest is text. */
function appendInline(parent: HTMLElement, text: string): void {
  for (const part of text.split(BOLD_SPLIT_RE)) {
    if (!part) continue;
    const bold = BOLD_MATCH_RE.exec(part);
    if (bold) {
      const strong = document.createElement('strong');
      strong.textContent = bold[1];
      parent.appendChild(strong);
    } else {
      parent.appendChild(document.createTextNode(part));
    }
  }
}

/**
 * Render `text` into `el` as paragraphs + lists. Call `renderMath(el)` after
 * this to typeset any LaTeX in the resulting text nodes.
 */
export function renderAnswer(el: HTMLElement, text: string): void {
  el.textContent = '';

  // Strip the raw corpus-slug citations the model leaves inline, e.g.
  // "[the-line-5-perpendicular-distance-from-a-point-to-a-line]". These are
  // multi-word kebab-case tokens in square brackets; the clickable source
  // cards below the answer already attribute the tutorial. (Display-math
  // delimiters use backslash-brackets "\[ \]", so this never touches maths.)
  text = text.replace(/\s*\[[a-z0-9]+(?:-[a-z0-9]+)+\]/g, '');

  let para: string[] = [];
  let listEl: HTMLUListElement | HTMLOListElement | null = null;
  let listType: 'ul' | 'ol' | null = null;

  const flushPara = () => {
    if (para.length === 0) return;
    const p = document.createElement('p');
    appendInline(p, para.join('\n'));
    el.appendChild(p);
    para = [];
  };
  const endList = () => {
    listEl = null;
    listType = null;
  };

  for (const line of text.split('\n')) {
    if (line.trim() === '') {
      flushPara();
      endList();
      continue;
    }

    const ul = UL_RE.exec(line);
    const ol = ul ? null : OL_RE.exec(line);

    if (ul || ol) {
      flushPara();
      const wantType: 'ul' | 'ol' = ul ? 'ul' : 'ol';
      if (!listEl || listType !== wantType) {
        endList();
        listEl = document.createElement(wantType) as
          | HTMLUListElement
          | HTMLOListElement;
        listEl.className = 'gktuition-tutor__list';
        listType = wantType;
        el.appendChild(listEl);
      }
      const li = document.createElement('li');
      appendInline(li, (ul ? ul[1] : ol![1]).trim());
      listEl.appendChild(li);
    } else {
      endList();
      para.push(line);
    }
  }

  flushPara();
  endList();

  // Defensive: never leave the bubble blank (e.g. odd input) — fall back to
  // the raw text so the answer is always visible.
  if (!el.firstChild && text) el.textContent = text;
}
