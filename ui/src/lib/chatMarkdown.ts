import katex from "katex";
import type { Components, PluginConfig } from "@pierre/words/react";

import {
  getMermaidResult,
  renderMermaid,
  type MermaidTheme,
  type MermaidResult,
} from "@/lib/chatMermaid";
import { getChatCodePlugin } from "@/lib/highlight";

/**
 * Chat answers render with @pierre/words, which takes HTML-string hooks and
 * plugins instead of React components. This module holds the source
 * preparation and those hooks; `ChatMarkdown` wires them to the page.
 */

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function decodeAttribute(value: string): string {
  return value
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");
}

/**
 * Models write LaTeX as \( \) and \[ \] as often as $ and $$, but the Markdown
 * renderer only understands dollars. Rewrite the bracket forms outside code spans.
 */
export function normalizeMathDelimiters(markdown: string): string {
  return markdown
    .split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g)
    .map((part, i) => {
      if (i % 2 === 1) return part;
      return part
        .replace(/\\\[([\s\S]+?)\\\]/g, (_, expr: string) => `\n$$\n${expr.trim()}\n$$\n`)
        .replace(/\\\(([\s\S]+?)\\\)/g, (_, expr: string) => `$${expr}$`);
    })
    .join("");
}

// A fence may sit inside block quotes; list indentation is allowed too.
const FENCE_OPEN = /^(?:[ \t]*>)*[ \t]*(`{3,}|~{3,})/;
const LIST_ITEM = /^[ \t]{0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)/;
const INDENTED_CODE = /^(?: {4}|\t)/;
// URI and email autolinks, which CommonMark reads as links rather than HTML.
const AUTOLINK = /<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*|[^\s<>@]+@[^\s<>]+)>/y;
// The characters after `<` that can start an HTML tag, comment or declaration.
const TAG_START = /[A-Za-z/!?]/;
const INLINE_SPECIAL = /[`\\$<]/g;

function closesFence(line: string, marker: string): boolean {
  const match = /^(?:[ \t]*>)*[ \t]*(`{3,}|~{3,})[ \t]*$/.exec(line);
  return match !== null && match[1][0] === marker[0] && match[1].length >= marker.length;
}

function backtickRun(text: string, at: number): number {
  let end = at;
  while (text.charCodeAt(end) === 96) end++;
  return end - at;
}

/** The end of the code span that opens at `at`, or -1 when it is not closed. */
function codeSpanEnd(text: string, at: number, length: number): number {
  for (let from = at + length; ;) {
    const next = text.indexOf("`", from);
    if (next < 0) return -1;
    const run = backtickRun(text, next);
    if (run === length) return next + run;
    from = next + run;
  }
}

/** The end of inline `$...$` math opening at `at`, or -1. Mirrors the renderer's rule. */
function inlineMathEnd(text: string, at: number): number {
  const first = text[at + 1];
  if (first === undefined || first === "$" || /\s/.test(first)) return -1;
  for (let close = text.indexOf("$", at + 1); close > 0; close = text.indexOf("$", close + 1)) {
    const between = text.slice(at + 1, close);
    if (between.includes("\n")) return -1;
    if (text[close - 1] === "\\" || /\s/.test(text[close - 1])) continue;
    if (/\d/.test(text[close + 1] ?? "")) return -1;
    return close + 1;
  }
  return -1;
}

/** Escape `<` that would start raw HTML in a run of Markdown text, outside code and math. */
function escapeInlineHtml(text: string, streaming: boolean): string {
  let result = "";
  let from = 0;
  INLINE_SPECIAL.lastIndex = 0;
  for (let match = INLINE_SPECIAL.exec(text); match !== null; match = INLINE_SPECIAL.exec(text)) {
    const at = match.index;
    let skip = at + 1;
    const char = text[at];
    if (char === "\\") {
      skip = at + 2;
    } else if (char === "`") {
      const run = backtickRun(text, at);
      const end = codeSpanEnd(text, at, run);
      if (end >= 0) skip = end;
      else if (streaming) {
        // The span is still being written: keep the rest of the line verbatim.
        const line = text.indexOf("\n", at);
        skip = line < 0 ? text.length : line;
      } else skip = at + run;
    } else if (char === "$") {
      if (text[at + 1] === "$") {
        const close = text.indexOf("$$", at + 2);
        if (close >= 0) skip = close + 2;
        else skip = streaming ? text.length : at + 2;
      } else {
        const end = inlineMathEnd(text, at);
        if (end >= 0) skip = end;
      }
    } else {
      AUTOLINK.lastIndex = at;
      if (AUTOLINK.test(text)) skip = AUTOLINK.lastIndex;
      else if (TAG_START.test(text[at + 1] ?? "") && !text.endsWith("](", at)) {
        result += `${text.slice(from, at)}\\<`;
        from = at + 1;
      }
    }
    INLINE_SPECIAL.lastIndex = Math.min(skip, text.length);
  }
  return result + text.slice(from);
}

/**
 * Raw HTML in an answer shows as text, as it always has: the renderer would
 * otherwise drop it, together with the text inside a block of HTML. Escaping
 * skips fenced and indented code, code spans, math and autolinks. While the
 * answer streams, an unclosed code span or display math keeps its tail as is.
 */
export function escapeRawHtml(markdown: string, { streaming = false } = {}): string {
  if (!markdown.includes("<")) return markdown;
  const lines = markdown.split("\n");
  const output: string[] = [];
  let text: string[] = [];
  let fence: string | null = null;
  let indented = false;
  let previousBlank = true;
  let inList = false;

  const flush = () => {
    if (text.length === 0) return;
    output.push(escapeInlineHtml(text.join("\n"), streaming));
    text = [];
  };

  for (const line of lines) {
    if (fence !== null) {
      output.push(line);
      if (closesFence(line, fence)) fence = null;
      continue;
    }
    const blank = line.trim() === "";
    if (indented && (blank || INDENTED_CODE.test(line))) {
      output.push(line);
      previousBlank = blank;
      continue;
    }
    indented = false;
    const open = FENCE_OPEN.exec(line);
    // A backtick fence's info string cannot contain a backtick.
    if (open && !(open[1][0] === "`" && line.slice(open[0].length).includes("`"))) {
      flush();
      output.push(line);
      fence = open[1];
      previousBlank = false;
      continue;
    }
    if (!blank && previousBlank && !inList && INDENTED_CODE.test(line)) {
      flush();
      output.push(line);
      indented = true;
      previousBlank = false;
      continue;
    }
    if (LIST_ITEM.test(line)) inList = true;
    else if (!blank && previousBlank && !/^[ \t]/.test(line)) inList = false;
    if (blank) {
      flush();
      output.push(line);
    } else {
      text.push(line);
    }
    previousBlank = blank;
  }
  flush();
  return output.join("\n");
}

/** Prepare an answer for the renderer: dollar math, and raw HTML kept as text. */
export function prepareChatMarkdown(markdown: string, streaming: boolean): string {
  return escapeRawHtml(normalizeMathDelimiters(markdown), { streaming });
}

const MARKDOWN_LINK = /^<a data-markdown="(a|incomplete-link)"([^>]*)>/;

/**
 * Links open in a new tab, and `ChatMarkdown` turns clicks on QDash records
 * into previews. A link whose URL is still streaming, or whose URL the
 * renderer blocked, shows only its label. Anchors inside diagrams are left alone.
 */
function linkHook(html: string): string {
  const match = MARKDOWN_LINK.exec(html);
  if (!match) return html;
  const body = html.slice(match[0].length, -"</a>".length);
  if (match[1] === "incomplete-link") return `<span data-incomplete="true">${body}</span>`;
  const href = /\shref="([^"]*)"/.exec(match[2])?.[1];
  if (href === undefined) return `<span data-markdown="blocked-link">${body}</span>`;
  if (href.startsWith("#")) return html;
  return `<a data-markdown="a"${match[2]} target="_blank" rel="noopener noreferrer">${body}</a>`;
}

const MATH_SVG = /^<svg[^>]*\sdata-markdown="(math|math-display)"/;

/**
 * The renderer finds math and draws it as SVG; KaTeX redraws it from the TeX
 * source the renderer keeps in the SVG's label, so formulas keep KaTeX's
 * coverage and look.
 */
function mathHook(html: string): string {
  const kind = MATH_SVG.exec(html)?.[1];
  if (!kind) return html;
  const label = /\saria-label="([^"]*)"/.exec(html)?.[1];
  if (label === undefined) return html;
  return katex.renderToString(decodeAttribute(label).trim(), {
    displayMode: kind === "math-display",
    throwOnError: false,
    strict: false,
  });
}

/** Element hooks. Keep this object stable: a new set of hook names re-renders everything. */
export const chatMarkdownComponents: Components = {
  a: linkHook,
  inlineCode: (html) => html.replace("<code ", '<code class="chat-inline-code" '),
  table: (html) => `<div class="chat-table-wrap">${html}</div>`,
  svg: mathHook,
};

// Lucide icon paths (ISC license), inlined because diagram controls are HTML strings.
const ICON_PATHS = {
  zoomIn:
    '<circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/><line x1="11" x2="11" y1="8" y2="14"/><line x1="8" x2="14" y1="11" y2="11"/>',
  zoomOut:
    '<circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/><line x1="8" x2="14" y1="11" y2="11"/>',
  reset: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  fullscreen:
    '<path d="M15 3h6v6"/><path d="m21 3-7 7"/><path d="m3 21 7-7"/><path d="M9 21H3v-6"/>',
} as const;

function icon(name: keyof typeof ICON_PATHS): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="size-3.5" aria-hidden="true">${ICON_PATHS[name]}</svg>`;
}

export type MermaidAction = "zoom-in" | "zoom-out" | "reset" | "copy" | "fullscreen";

function actionButton(action: MermaidAction, label: string, name: keyof typeof ICON_PATHS) {
  return `<button type="button" class="btn btn-ghost btn-xs btn-square text-base-content/50 hover:text-base-content" data-mermaid-action="${action}" aria-label="${label}" title="${label}">${icon(name)}</button>`;
}

const DIAGRAM_HEADER = `<div class="flex items-center justify-between border-b border-base-300/50 bg-base-300/30 px-3 py-1 text-xs"><span class="font-mono text-base-content/50">mermaid</span><span class="flex items-center gap-0.5">${actionButton("zoom-out", "Zoom out", "zoomOut")}${actionButton("zoom-in", "Zoom in", "zoomIn")}${actionButton("reset", "Reset view", "reset")}${actionButton("copy", "Copy diagram source", "copy")}${actionButton("fullscreen", "Open fullscreen", "fullscreen")}</span></div>`;

const DIAGRAM_FRAME =
  "chat-mermaid not-prose my-3 overflow-hidden rounded-[var(--radius-box)] border border-base-300/70";

/** A code block with a copy button, in the markup the renderer uses for its own. */
function codeBlockHtml(code: string, language: string): string {
  const escaped = escapeHtml(code);
  return `<div data-markdown="code-block" data-language="${language}" data-code="${escaped}"><div data-markdown="code-header"><span>${language}</span><span><button type="button" data-code-action="copy" aria-label="Copy code">Copy</button></span></div><pre dir="ltr"><code data-markdown="code" class="language-${language}"><span data-markdown="code-lines">${escaped}</span></code></pre></div>`;
}

function mermaidDiagramHtml(source: string, svg: string): string {
  return `<div class="${DIAGRAM_FRAME}" data-chat-mermaid="ready" data-source="${escapeHtml(source)}">${DIAGRAM_HEADER}<div class="chat-mermaid-viewport" data-mermaid-viewport role="img" aria-label="Mermaid chart"><div class="chat-mermaid-canvas" data-mermaid-canvas>${svg}</div></div></div>`;
}

function mermaidErrorHtml(source: string, message: string): string {
  return `<div class="my-3" data-testid="chat-mermaid-error"><p class="mb-1 text-xs text-base-content/50">This diagram could not be displayed: ${escapeHtml(message)}</p>${codeBlockHtml(source, "mermaid")}</div>`;
}

const MERMAID_LOADING = `<div class="${DIAGRAM_FRAME}" data-chat-mermaid="loading"><div class="flex items-center gap-2 px-3 py-6 text-xs text-base-content/50"><span class="loading loading-spinner loading-xs" aria-hidden="true"></span>Rendering diagram</div></div>`;

/**
 * Plugins for one answer. Code uses the highlighter that is loaded when they
 * are created, so callers create them again once Highlights is ready. Mermaid
 * renders asynchronously, but the renderer wants HTML now: a diagram that has
 * not rendered yet shows a loading frame, and `onSettled` asks for a new
 * plugin object once it has, which makes the renderer format the answer again
 * with the cached result.
 */
export interface ChatDiagramCache {
  results: Map<string, MermaidResult>;
  pending: Set<string>;
}

export function createChatPlugins(
  theme: MermaidTheme,
  onSettled: () => void,
  diagrams: ChatDiagramCache,
): PluginConfig {
  return {
    code: getChatCodePlugin(),
    renderers: [
      {
        language: "mermaid",
        render({ code, isIncomplete }) {
          // Until the fence closes, the diagram shows as code.
          if (isIncomplete) return null;
          const source = code.replace(/\n$/, "");
          const result = diagrams.results.get(source) ?? getMermaidResult(source, theme);
          if (result) diagrams.results.set(source, result);
          if (result?.status === "ok") return mermaidDiagramHtml(source, result.svg);
          if (result?.status === "error") return mermaidErrorHtml(source, result.message);
          if (typeof window !== "undefined" && !diagrams.pending.has(source)) {
            diagrams.pending.add(source);
            void renderMermaid(source, theme).then((result) => {
              diagrams.results.set(source, result);
              diagrams.pending.delete(source);
              onSettled();
            });
          }
          return MERMAID_LOADING;
        },
      },
    ],
  };
}
