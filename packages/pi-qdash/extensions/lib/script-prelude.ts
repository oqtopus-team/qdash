import { calibrationDefinitionsSource } from "@oqtopus-team/qdash-sdk/calibration";

import { SCRIPT_OPTIONS_PREFIX, withScriptDeadline } from "./tool-policy.js";

/**
 * Pure helpers a Code Mode script can use without a tool call, shared by the pi CLI
 * (script-policy.ts) and the QDash Agent Runtime (agent-runtime/src/codemode.ts).
 *
 * Code Mode scripts cannot import modules, so both hosts add the helpers to a script's source:
 * `qdash.calibration` is the SDK's calibration builders
 * (`@oqtopus-team/qdash-sdk/calibration`), evaluated from the SDK's own implementation inside
 * the script's sandbox. They build spec JSON and nothing else: they read no globals beyond the
 * language's own, hold no tool, credential or network access, and a script still checks or runs
 * a spec only through the tools it may call (`tools.qdash_plan_pipeline`).
 *
 * The helpers are added only to a script that names `qdash`, so every other script runs exactly
 * as written. They go on one line after the script's options line and after its directive
 * prologue (`"use strict";` and any other leading string-literal statements), so the script's
 * directives keep their effect and line numbers in errors still match what the model wrote.
 */

/** The global a script reads the helpers from: `qdash.calibration`. */
export const SCRIPT_HELPERS_GLOBAL = "qdash";

const NAMES_HELPERS = /\bqdash\b/;

let preludeLine: string | undefined;

/**
 * One line of JavaScript that defines the frozen `qdash` global. The helpers' source is
 * evaluated from a string literal, so its own line breaks and comments cannot change the
 * script's lines.
 */
export function scriptPreludeLine(): string {
  preludeLine ??= (() => {
    const install = [
      "(function () {",
      `  var calibration = ${calibrationDefinitionsSource()};`,
      "  var helpers = Object.freeze({ calibration: calibration });",
      `  Object.defineProperty(globalThis, ${JSON.stringify(SCRIPT_HELPERS_GLOBAL)}, { value: helpers, writable: false, enumerable: false, configurable: false });`,
      "})();",
    ].join("\n");
    // JSON escapes every line break but U+2028 and U+2029, which end a line in a script too.
    const literal = JSON.stringify(install).replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
    return `(0, globalThis.eval)(${literal});`;
  })();
  return preludeLine;
}

/** JavaScript WhiteSpace (ECMA-262 12.2), excluding line terminators. */
const WHITESPACE = /[\t\v\f \u00a0\ufeff\p{Zs}]/u;
const LINE_TERMINATOR = /[\n\r\u2028\u2029]/;
/** `in` and `instanceof` continue an expression; any other identifier starts a new statement. */
const RELATIONAL_KEYWORD = /^(?:instanceof|in)(?![\p{ID_Continue}$\u200c\u200d\\])/u;

/**
 * The index of the first token at or after `index`, past whitespace and comments, and whether a
 * line terminator came before it; undefined for an unterminated block comment.
 */
function skipTrivia(source: string, index: number): { index: number; newline: boolean } | undefined {
  let i = index;
  let newline = false;
  while (i < source.length) {
    const ch = source[i] as string;
    if (LINE_TERMINATOR.test(ch)) {
      newline = true;
      i += 1;
    } else if (WHITESPACE.test(ch)) {
      i += 1;
    } else if (source.startsWith("//", i)) {
      i += 2;
      while (i < source.length && !LINE_TERMINATOR.test(source[i] as string)) i += 1;
    } else if (source.startsWith("/*", i)) {
      const close = source.indexOf("*/", i + 2);
      if (close === -1) return undefined;
      if (LINE_TERMINATOR.test(source.slice(i + 2, close))) newline = true;
      i = close + 2;
    } else {
      break;
    }
  }
  return { index: i, newline };
}

/** The index just past the string literal starting at `index`; undefined if it is unterminated. */
function skipStringLiteral(source: string, index: number): number | undefined {
  const quote = source[index];
  let i = index + 1;
  while (i < source.length) {
    const ch = source[i] as string;
    if (ch === quote) return i + 1;
    if (ch === "\\") {
      // An escape, or a line continuation (`\r\n` counts as one line terminator).
      i += source.startsWith("\r\n", i + 1) ? 3 : 2;
    } else if (ch === "\n" || ch === "\r") {
      return undefined;
    } else {
      i += 1;
    }
  }
  return undefined;
}

/**
 * Whether the token at `index`, which follows a string literal on a later line, continues that
 * string's expression, so no semicolon is inserted (ECMA-262 12.10) and the string is not a
 * directive. `++` and `--` cannot follow on a later line, and `!` only as `!=` or `!==`.
 */
function continuesExpression(source: string, index: number): boolean {
  const ch = source[index] as string;
  if ("([.`,?=*%<>&|^/".includes(ch)) return true;
  if (ch === "+" || ch === "-") return source[index + 1] !== ch;
  if (ch === "!") return source[index + 1] === "=";
  return RELATIONAL_KEYWORD.test(source.slice(index, index + 11));
}

/**
 * Where the helpers go in a script body starting at `start`: just past its directive prologue
 * (ECMA-262 11.2.1), the leading statements that are a string literal alone, ended by `;`, by a
 * line break that inserts a semicolon, or by the end of the script. `semicolon` says the last
 * directive ended without one, so the helpers must add it. A string literal that continues into
 * an expression (`"use strict" + x`) ends the prologue without being a directive.
 */
export function directivePrologueEnd(source: string, start = 0): { index: number; semicolon: boolean } {
  let end = { index: start, semicolon: false };
  let i = start;
  for (;;) {
    const token = skipTrivia(source, i);
    if (token === undefined) return end;
    const quote = source[token.index];
    if (quote !== '"' && quote !== "'") return end;
    const literalEnd = skipStringLiteral(source, token.index);
    if (literalEnd === undefined) return end;
    const next = skipTrivia(source, literalEnd);
    if (next === undefined) return end;
    const ch = source[next.index];
    if (ch === ";") {
      end = { index: next.index + 1, semicolon: false };
    } else if (ch === undefined || ch === "}" || (next.newline && !continuesExpression(source, next.index))) {
      end = { index: literalEnd, semicolon: true };
    } else {
      return end;
    }
    i = end.index;
  }
}

/**
 * The script with the helpers added when it names `qdash`. A script without an options line, or
 * whose options line has no code after it, is returned unchanged for Code Mode to run or reject
 * as it is. The helpers follow the script's directive prologue on the same line, so a
 * `"use strict"` the script starts with still applies to all of its code.
 */
export function withScriptHelpers(source: string, prefix: string = SCRIPT_OPTIONS_PREFIX): string {
  if (!NAMES_HELPERS.test(source)) return source;
  const newline = source.indexOf("\n");
  if (newline === -1) return source;
  if (!source.slice(0, newline).trimStart().startsWith(prefix)) return source;
  const { index, semicolon } = directivePrologueEnd(source, newline + 1);
  return `${source.slice(0, index)}${semicolon ? ";" : ""}${scriptPreludeLine()}${source.slice(index)}`;
}

/** What a host runs for a script: a bounded deadline, then the helpers when it uses them. */
export function prepareScriptSource(source: string, prefix: string = SCRIPT_OPTIONS_PREFIX): string {
  return withScriptHelpers(withScriptDeadline(source, prefix), prefix);
}
