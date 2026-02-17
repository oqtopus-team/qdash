"use client";

import React, { useState, useCallback } from "react";
import { Copy, Check } from "lucide-react";

interface CodeBlockProps {
  language?: string;
  children: string;
}

// Minimal keyword-based syntax highlighting using CSS variables
const PYTHON_KEYWORDS = new Set([
  "import",
  "from",
  "as",
  "def",
  "class",
  "return",
  "if",
  "elif",
  "else",
  "for",
  "while",
  "in",
  "not",
  "and",
  "or",
  "is",
  "with",
  "try",
  "except",
  "finally",
  "raise",
  "pass",
  "break",
  "continue",
  "yield",
  "lambda",
  "True",
  "False",
  "None",
  "print",
  "len",
  "range",
  "type",
  "isinstance",
]);

const PYTHON_BUILTINS = new Set([
  "dict",
  "list",
  "set",
  "tuple",
  "int",
  "float",
  "str",
  "bool",
  "sorted",
  "enumerate",
  "zip",
  "map",
  "filter",
  "sum",
  "min",
  "max",
  "abs",
  "round",
]);

function highlightPython(code: string): React.ReactNode[] {
  const lines = code.split("\n");
  return lines.map((line, lineIdx) => {
    const tokens: React.ReactNode[] = [];
    // Simple tokenizer: comments, strings, numbers, keywords
    let i = 0;
    while (i < line.length) {
      // Comment
      if (line[i] === "#") {
        tokens.push(
          <span key={`${lineIdx}-${i}`} className="text-base-content/40 italic">
            {line.slice(i)}
          </span>,
        );
        i = line.length;
        continue;
      }
      // String (single or double quotes)
      if (line[i] === '"' || line[i] === "'") {
        const quote = line[i];
        let j = i + 1;
        while (j < line.length && line[j] !== quote) {
          if (line[j] === "\\") j++; // skip escaped char
          j++;
        }
        j = Math.min(j + 1, line.length);
        tokens.push(
          <span key={`${lineIdx}-${i}`} className="text-success">
            {line.slice(i, j)}
          </span>,
        );
        i = j;
        continue;
      }
      // f-string prefix
      if (
        (line[i] === "f" || line[i] === "r" || line[i] === "b") &&
        i + 1 < line.length &&
        (line[i + 1] === '"' || line[i + 1] === "'")
      ) {
        const quote = line[i + 1];
        let j = i + 2;
        while (j < line.length && line[j] !== quote) {
          if (line[j] === "\\") j++;
          j++;
        }
        j = Math.min(j + 1, line.length);
        tokens.push(
          <span key={`${lineIdx}-${i}`} className="text-success">
            {line.slice(i, j)}
          </span>,
        );
        i = j;
        continue;
      }
      // Number
      if (
        /\d/.test(line[i]) &&
        (i === 0 || /[\s(=,[\-+*/%<>]/.test(line[i - 1]))
      ) {
        let j = i;
        while (j < line.length && /[\d._eE+\-]/.test(line[j])) j++;
        tokens.push(
          <span key={`${lineIdx}-${i}`} className="text-info">
            {line.slice(i, j)}
          </span>,
        );
        i = j;
        continue;
      }
      // Word (keyword/builtin/identifier)
      if (/[a-zA-Z_]/.test(line[i])) {
        let j = i;
        while (j < line.length && /[a-zA-Z0-9_]/.test(line[j])) j++;
        const word = line.slice(i, j);
        if (PYTHON_KEYWORDS.has(word)) {
          tokens.push(
            <span
              key={`${lineIdx}-${i}`}
              className="text-primary font-semibold"
            >
              {word}
            </span>,
          );
        } else if (PYTHON_BUILTINS.has(word)) {
          tokens.push(
            <span key={`${lineIdx}-${i}`} className="text-secondary">
              {word}
            </span>,
          );
        } else {
          tokens.push(<span key={`${lineIdx}-${i}`}>{word}</span>);
        }
        i = j;
        continue;
      }
      // Operators and punctuation
      tokens.push(<span key={`${lineIdx}-${i}`}>{line[i]}</span>);
      i++;
    }
    return (
      <React.Fragment key={lineIdx}>
        {tokens}
        {lineIdx < lines.length - 1 ? "\n" : null}
      </React.Fragment>
    );
  });
}

export function CodeBlock({ language, children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [children]);

  const isPython = language === "python" || language === "py";

  return (
    <div className="relative group my-2 rounded-lg overflow-hidden border border-base-300 bg-base-200">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1 bg-base-300/50 text-xs text-base-content/50">
        <span>{language || "code"}</span>
        <button
          onClick={handleCopy}
          className="btn btn-ghost btn-xs gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3" />
              Copied
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
      <pre className="overflow-x-auto px-3 py-2 text-xs leading-relaxed">
        <code>{isPython ? highlightPython(children) : children}</code>
      </pre>
    </div>
  );
}
