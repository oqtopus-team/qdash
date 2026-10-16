"use client";

import { useState, useCallback, useMemo } from "react";
import { Copy, Check } from "lucide-react";
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

interface CodeBlockProps {
  language?: string;
  children: string;
}

/** Highlighted HTML for a known language, or null to render the code as plain text. */
function highlight(code: string, language?: string): string | null {
  if (!language || !hljs.getLanguage(language)) return null;
  try {
    return hljs.highlight(code, { language, ignoreIllegals: true }).value;
  } catch {
    return null;
  }
}

export function CodeBlock({ language, children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(children).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      },
      () => {
        // Clipboard can be unavailable on insecure origins; keep the button idle.
      },
    );
  }, [children]);

  const html = useMemo(() => highlight(children, language), [children, language]);

  return (
    <div className="relative group my-3 rounded-xl overflow-hidden border border-base-300/70 bg-base-200/80 not-prose">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-base-300/30 text-xs border-b border-base-300/50">
        <span className="font-mono text-base-content/50 text-[11px] lowercase tracking-wide">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className={`btn btn-ghost btn-xs gap-1 transition-colors ${
            copied ? "text-success" : "text-base-content/50 hover:text-base-content"
          }`}
          aria-label={copied ? "Code copied" : "Copy code"}
        >
          {copied ? (
            <>
              <Check className="w-3 h-3" />
              <span aria-live="polite">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              Copy
            </>
          )}
        </button>
      </div>
      {/* Code content */}
      <pre className="overflow-x-auto px-4 py-3 text-xs leading-relaxed font-mono">
        {html !== null ? (
          // hljs escapes the source, so its output is safe to inject.
          <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} />
        ) : (
          <code>{children}</code>
        )}
      </pre>
    </div>
  );
}
