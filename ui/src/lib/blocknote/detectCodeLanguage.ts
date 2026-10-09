import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import yaml from "highlight.js/lib/languages/yaml";

hljs.registerLanguage("bash", bash);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("python", python);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("yaml", yaml);

const HLJS_LANGUAGE_SUBSET = [
  "python",
  "bash",
  "json",
  "yaml",
  "sql",
  "typescript",
  "javascript",
  "markdown",
];

const HLJS_TO_BLOCKNOTE_LANGUAGE: Record<string, string> = {
  bash: "shellscript",
  javascript: "javascript",
  json: "json",
  markdown: "markdown",
  python: "python",
  sql: "sql",
  typescript: "typescript",
  yaml: "yaml",
};

const MIN_RELEVANCE = 2;

/** Returns whether `trimmed` is a JSON object or array literal. */
function detectJson(trimmed: string): boolean {
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return false;
  try {
    JSON.parse(trimmed);
    return true;
  } catch {
    return false;
  }
}

/** Returns a BlockNote code block language id for `code`, or `null` when unsure. */
export function detectCodeLanguage(code: string): string | null {
  const trimmed = code.trim();
  if (!trimmed) return null;
  if (detectJson(trimmed)) return "json";

  const result = hljs.highlightAuto(trimmed, HLJS_LANGUAGE_SUBSET);
  if (!result.language || result.relevance < MIN_RELEVANCE) return null;
  if (result.relevance <= (result.secondBest?.relevance ?? 0)) return null;
  return HLJS_TO_BLOCKNOTE_LANGUAGE[result.language] ?? null;
}
