import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import yaml from "highlight.js/lib/languages/yaml";

hljs.registerLanguage("bash", bash);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("python", python);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("yaml", yaml);
hljs.registerAliases(["py"], { languageName: "python" });
hljs.registerAliases(["sh", "shell", "zsh", "console"], { languageName: "bash" });
hljs.registerAliases(["js", "jsx"], { languageName: "javascript" });
hljs.registerAliases(["ts", "tsx"], { languageName: "typescript" });
hljs.registerAliases(["yml"], { languageName: "yaml" });

/**
 * Highlighted HTML for a known language, or null to render the code as plain
 * text. highlight.js escapes the source, so the result is safe to inject.
 */
export function highlightCode(code: string, language?: string): string | null {
  if (!language || !hljs.getLanguage(language)) return null;
  try {
    return hljs.highlight(code, { language, ignoreIllegals: true }).value;
  } catch {
    return null;
  }
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
