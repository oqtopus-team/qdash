import { useEffect, useSyncExternalStore } from "react";
import { canUseWASM } from "@pierre/diffs";
import type { CodeHighlighterPlugin, CodeHighlighterSession } from "@pierre/words/react";
import type { Theme } from "@pierre/highlights";
import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import yaml from "highlight.js/lib/languages/yaml";

/**
 * Syntax highlighting for chat code: answers rendered by @pierre/words and
 * `CodeBlock`. Highlights (@pierre/highlights, WebAssembly lexers for 150+
 * languages) loads on demand in the browser. Until it has loaded, and where
 * WebAssembly or SIMD is missing or blocked, highlight.js highlights the
 * common languages below.
 */

hljs.registerLanguage("bash", bash);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("python", python);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("yaml", yaml);
hljs.registerAliases(["py"], { languageName: "python" });
hljs.registerAliases(["sh", "shell", "zsh", "console"], {
  languageName: "bash",
});
hljs.registerAliases(["js", "jsx"], { languageName: "javascript" });
hljs.registerAliases(["ts", "tsx"], { languageName: "typescript" });
hljs.registerAliases(["yml"], { languageName: "yaml" });

export type CodeHighlighterEngine = "highlights" | "highlight.js";

/** The CSS custom property prefix of Highlights colors; globals.css maps them to DaisyUI. */
export const CODE_COLOR_PREFIX = "--qd-code-";

/**
 * A palette theme: each color is the suffix of a CSS variable, so token colors
 * follow the active DaisyUI theme without highlighting again. Scopes without
 * an entry inherit from their nearest parent, such as `keyword.control`.
 */
export const CODE_THEME: Theme = {
  name: "QDash",
  appearance: "dark",
  cssVariables: { prefix: CODE_COLOR_PREFIX },
  style: {
    syntax: {
      keyword: { color: "keyword", font_weight: 500 },
      tag: "keyword",
      selector: "keyword",
      "emphasis.strong": { color: "foreground", font_weight: 600 },
      emphasis: { color: "foreground", font_style: "italic" },
      string: "string",
      "string.special": "string",
      "text.literal": "string",
      link_uri: "string",
      "diff.plus": "string",
      number: "number",
      boolean: "number",
      constant: "number",
      enum: "number",
      variant: "number",
      "string.escape": "number",
      "string.special.symbol": "number",
      function: "title",
      type: "title",
      constructor: "title",
      title: "title",
      property: "title",
      attribute: "title",
      label: "title",
      comment: { color: "comment", font_style: "italic" },
      preproc: "comment",
      "diff.minus": "deletion",
    },
  },
};

const HIGHLIGHTS_OPTIONS = { theme: CODE_THEME } as const;

/** Fence names highlight.js accepts that Highlights spells differently. */
const LANGUAGE_ALIASES: Record<string, string> = { console: "shellsession" };

interface HighlightsRuntime {
  html(code: string, language: string): string | null;
  plugin: CodeHighlighterPlugin;
}

let runtime: HighlightsRuntime | null = null;
let loading: Promise<boolean> | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

const SPAN_TAG = /<span[^>]*>|<\/span>|\n/g;

/**
 * Close and reopen highlight spans at every line break, so each line is
 * balanced HTML. A renderer that groups lines (such as Words) can then split
 * a multi-line string or comment without losing its color.
 */
export function balanceHighlightedLines(html: string): string {
  const open: string[] = [];
  return html.replace(SPAN_TAG, (token) => {
    if (token === "\n") {
      if (open.length === 0) return token;
      return `${"</span>".repeat(open.length)}\n${open.join("")}`;
    }
    if (token === "</span>") open.pop();
    else open.push(token);
    return token;
  });
}

function hljsHighlight(code: string, language?: string): string | null {
  if (!language || !hljs.getLanguage(language)) return null;
  try {
    return hljs.highlight(code, { language, ignoreIllegals: true }).value;
  } catch {
    return null;
  }
}

function highlightsLanguage(language: string): string {
  return LANGUAGE_ALIASES[language.toLowerCase()] ?? language;
}

/**
 * Highlighted HTML for a known language, or null to render the code as plain
 * text. Both highlighters escape the source, so the result is safe to inject.
 */
export function highlightCode(code: string, language?: string): string | null {
  if (!language) return null;
  if (runtime) {
    const html = runtime.html(code, highlightsLanguage(language));
    if (html !== null) return html;
  }
  return hljsHighlight(code, language);
}

/** highlight.js, for Words, until Highlights has loaded. */
const hljsPlugin: CodeHighlighterPlugin = {
  highlight({ code, language }) {
    const html = hljsHighlight(code, language);
    return html === null ? null : balanceHighlightedLines(html);
  },
};

/** Words' Highlights plugin, with its whole-block output balanced per line and errors as plain text. */
function wrapHighlightsPlugin(plugin: CodeHighlighterPlugin): CodeHighlighterPlugin {
  const createSession = plugin.createSession?.bind(plugin);
  return {
    highlight(options) {
      try {
        const html = plugin.highlight({
          ...options,
          language: highlightsLanguage(options.language),
        });
        return html === null ? hljsPlugin.highlight(options) : balanceHighlightedLines(html);
      } catch {
        return hljsPlugin.highlight(options);
      }
    },
    createSession: createSession
      ? () => {
          const session: CodeHighlighterSession = createSession();
          const map = <T extends { language: string }>(options: T): T => ({
            ...options,
            language: highlightsLanguage(options.language),
          });
          return {
            highlight(options) {
              try {
                return session.highlight(map(options));
              } catch {
                session.dispose();
                return null;
              }
            },
            highlightLines: session.highlightLines
              ? (options) => {
                  try {
                    return session.highlightLines?.(map(options)) ?? null;
                  } catch {
                    session.dispose();
                    return null;
                  }
                }
              : undefined,
            dispose: () => session.dispose(),
          };
        }
      : undefined,
  };
}

/**
 * Load Highlights once. Resolves true when it is ready, and false where it
 * cannot run: on the server, without WebAssembly SIMD (or with WebAssembly
 * blocked by a Content Security Policy), or when its module fails to load.
 * highlight.js stays in use in those cases.
 */
export function loadHighlights(): Promise<boolean> {
  if (runtime) return Promise.resolve(true);
  if (typeof window === "undefined") return Promise.resolve(false);
  loading ??= (async () => {
    if (!canUseWASM()) return false;
    try {
      const [core, words] = await Promise.all([
        import("@pierre/highlights"),
        import("@pierre/words/highlights"),
      ]);
      const decoder = new TextDecoder();
      const html = (code: string, language: string): string | null => {
        if (!core.isSupportedLanguage(language)) return null;
        try {
          const markup = decoder.decode(
            core.codeToHtml(code, { ...HIGHLIGHTS_OPTIONS, lang: language }),
          );
          return markup.slice(markup.indexOf("<code>") + 6, markup.lastIndexOf("</code>"));
        } catch {
          return null;
        }
      };
      // Instantiating the lexer is the step a blocked or broken WebAssembly fails.
      if (html("x", "plain") === null) return false;
      runtime = {
        html,
        plugin: wrapHighlightsPlugin(words.createHighlightsPlugin(HIGHLIGHTS_OPTIONS)),
      };
      notify();
      return true;
    } catch (error) {
      console.warn("Highlights is unavailable; using highlight.js for code.", error);
      return false;
    }
  })();
  return loading;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getEngine(): CodeHighlighterEngine {
  return runtime ? "highlights" : "highlight.js";
}

function getServerEngine(): CodeHighlighterEngine {
  return "highlight.js";
}

/**
 * The highlighter in use, starting Highlights' load on mount. Components
 * render again with Highlights once it is ready; the server and the first
 * client render use highlight.js, so hydration matches.
 */
export function useCodeHighlighter(enabled = true): CodeHighlighterEngine {
  const engine = useSyncExternalStore(subscribe, getEngine, getServerEngine);
  useEffect(() => {
    if (enabled) void loadHighlights();
  }, [enabled]);
  return engine;
}

/** The Words code plugin for the current highlighter. */
export function getChatCodePlugin(): CodeHighlighterPlugin {
  return runtime?.plugin ?? hljsPlugin;
}
