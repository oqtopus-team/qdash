/**
 * Downloads for what Copilot generates: an answer as Markdown, a code block,
 * and the content the agent's `write` calls sent to its workspace. Everything
 * is built in the browser from what the chat already holds; no server path is
 * fetched, and a written file is offered as the content that call wrote, not
 * as the file's current state in the workspace.
 */

import { saveBlob } from "@/lib/utils/download";

import type { CopilotBlocksResult, TraceStep } from "@/types/copilotChat";

/** Longest file name offered, extension included. */
const MAX_FILE_NAME = 120;

const EXTENSION_BY_LANGUAGE: Record<string, string> = {
  python: "py",
  py: "py",
  bash: "sh",
  sh: "sh",
  shell: "sh",
  zsh: "sh",
  console: "sh",
  javascript: "js",
  js: "js",
  jsx: "jsx",
  typescript: "ts",
  ts: "ts",
  tsx: "tsx",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  sql: "sql",
  markdown: "md",
  md: "md",
  csv: "csv",
  html: "html",
  toml: "toml",
  xml: "xml",
  ini: "ini",
  go: "go",
  rust: "rs",
  rs: "rs",
  c: "c",
  cpp: "cpp",
  java: "java",
  r: "r",
  mermaid: "mmd",
};

const MIME_BY_EXTENSION: Record<string, string> = {
  md: "text/markdown",
  csv: "text/csv",
  json: "application/json",
  html: "text/html",
};

/**
 * A safe local file name: the last path segment only, without characters a
 * file system rejects, never empty or hidden.
 */
export function safeFileName(name: string, fallback = "download.txt"): string {
  const base = name.split(/[\\/]/).pop() ?? "";
  const cleaned = base
    // eslint-disable-next-line no-control-regex -- strip control characters
    .replace(/[\u0000-\u001f\u007f<>:"|?*]+/g, "_")
    .replace(/^[.\s]+/, "")
    .trim();
  if (!cleaned) return fallback;
  if (cleaned.length <= MAX_FILE_NAME) return cleaned;
  const dot = cleaned.lastIndexOf(".");
  const extension = dot > 0 && cleaned.length - dot <= 10 ? cleaned.slice(dot) : "";
  return cleaned.slice(0, MAX_FILE_NAME - extension.length) + extension;
}

/** The file extension for a code block's language, `txt` when unknown. */
function extensionForLanguage(language?: string): string {
  // A `lang:path` info string can reach the renderer as the language.
  const name = language?.split(":")[0].toLowerCase();
  return (name && EXTENSION_BY_LANGUAGE[name]) || "txt";
}

/** The file name for a code block: its title's file name when it has one, else `snippet.<ext>`. */
export function codeFileName(language?: string, title?: string): string {
  const extension = extensionForLanguage(language);
  const fallback = `snippet.${extension}`;
  if (!title) return fallback;
  const name = safeFileName(title, fallback);
  return name.includes(".") ? name : `${name}.${extension}`;
}

function mimeFor(fileName: string): string {
  const extension = fileName.split(".").pop()?.toLowerCase() ?? "";
  return MIME_BY_EXTENSION[extension] ?? "text/plain";
}

/** Save text as a file through the browser's download, named by `fileName`. */
export function downloadText(fileName: string, text: string, mimeType = mimeFor(fileName)): void {
  saveBlob(new Blob([text], { type: `${mimeType};charset=utf-8` }), fileName);
}

function fence(code: string, language = ""): string {
  // A fence longer than any backtick run inside keeps the code intact.
  const longest = Math.max(2, ...(code.match(/`+/g) ?? []).map((run) => run.length));
  const marker = "`".repeat(longest + 1);
  return `${marker}${language}\n${code}\n${marker}`;
}

function parseBlocks(content: string): CopilotBlocksResult | null {
  if (!content.startsWith("{")) return null;
  try {
    const data = JSON.parse(content);
    return data && Array.isArray(data.blocks) ? (data as CopilotBlocksResult) : null;
  } catch {
    return null;
  }
}

/**
 * An assistant answer as a Markdown document: its text, and any code change
 * it proposed as a fenced block. Charts and interactive cards have no
 * Markdown form and are left out.
 */
export function answerMarkdown(content: string): string {
  const parsed = parseBlocks(content);
  if (!parsed) return `${content.trim()}\n`;
  const parts: string[] = [];
  for (const block of parsed.blocks) {
    if (block.type === "text" && block.content) {
      parts.push(block.content.trim());
    } else if (block.type === "edit" && block.edit) {
      parts.push(
        `**Proposed change to \`${block.edit.flowName}\`:** ${block.edit.summary}\n\n${fence(
          block.edit.code,
          "python",
        )}`,
      );
    }
  }
  return `${parts.filter(Boolean).join("\n\n")}\n`;
}

/** Whether an answer has anything to put in a Markdown download. */
export function hasAnswerMarkdown(content: string): boolean {
  return answerMarkdown(content).trim().length > 0;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/**
 * The name of an answer's Markdown file: its first heading, slugged, or a
 * timestamped default.
 */
export function answerFileName(content: string, now: Date = new Date()): string {
  const heading = /^#{1,6}\s+(.+)$/m.exec(answerMarkdown(content))?.[1];
  const slug = heading
    ?.replace(/[`*_~[\]()]/g, "")
    .trim()
    .replace(/[\s/\\]+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 60)
    .replace(/^-|-$/g, "");
  if (slug) return safeFileName(`${slug}.md`, "qdash-answer.md");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(
    now.getHours(),
  )}${pad(now.getMinutes())}`;
  return `qdash-answer-${stamp}.md`;
}

const FENCE_OPEN = /^((?:[ \t]*>)*)([ \t]*)(`{3,}|~{3,})(.*)$/;

/**
 * The file name a fence's info string gives: `title="…"`, `filename=…` or
 * `file=…`, `lang:path`, or a bare second word that looks like a file name.
 */
export function fenceTitle(info: string): string | undefined {
  const keyed = /(?:^|\s)(?:title|filename|file)=(?:"([^"]*)"|'([^']*)'|(\S+))/i.exec(info);
  if (keyed) return (keyed[1] ?? keyed[2] ?? keyed[3]).trim() || undefined;
  const [language = "", second] = info.trim().split(/\s+/);
  const colon = language.indexOf(":");
  if (colon > 0 && colon < language.length - 1) return language.slice(colon + 1);
  if (second && /^[\w.\-/\\]*\w\.[A-Za-z0-9]{1,10}$/.test(second)) return second;
  return undefined;
}

/** A fenced code block of a Markdown source: its code and the title its info string gives. */
export interface FencedCode {
  code: string;
  title?: string;
}

function stripLine(line: string, quotes: number, indent: number): string {
  let rest = line;
  for (let i = 0; i < quotes; i++) rest = rest.replace(/^[ \t]*>[ ]?/, "");
  let removed = 0;
  while (removed < indent && rest[removed] === " ") removed++;
  return rest.slice(removed);
}

/**
 * The fenced code blocks of a Markdown source, in order. The renderer drops a
 * fence's info string after the language, so a code block's title is read
 * from the source; blocks nested in lists or quotes are handled loosely, and
 * a block that does not match falls back to a name from its language.
 */
export function fencedCode(markdown: string): FencedCode[] {
  const lines = markdown.split("\n");
  const blocks: FencedCode[] = [];
  for (let i = 0; i < lines.length; i++) {
    const open = FENCE_OPEN.exec(lines[i]);
    if (!open) continue;
    const [, quoteRun, indentRun, marker, info] = open;
    if (marker[0] === "`" && info.includes("`")) continue;
    const quotes = (quoteRun.match(/>/g) ?? []).length;
    const indent = indentRun.replace(/\t/g, "    ").length;
    const close = new RegExp(`^(?:[ \\t]*>)*[ \\t]*${marker[0]}{${marker.length},}[ \\t]*$`);
    const body: string[] = [];
    let j = i + 1;
    for (; j < lines.length && !close.test(lines[j]); j++) {
      body.push(stripLine(lines[j], quotes, indent));
    }
    blocks.push({ code: body.join("\n"), title: fenceTitle(info) });
    i = j;
  }
  return blocks;
}

function sameCode(a: string, b: string): boolean {
  return a.replace(/\n+$/, "") === b.replace(/\n+$/, "");
}

/**
 * The title of the `occurrence`-th rendered block with this code, matched to
 * the source's fenced blocks with the same code.
 */
export function codeBlockTitle(markdown: string, code: string, occurrence = 0): string | undefined {
  return fencedCode(markdown).filter((block) => sameCode(block.code, code))[occurrence]?.title;
}

/** The `path` argument of a call, also from arguments the stored trace cut to a JSON prefix. */
function argsPath(args: unknown): string | undefined {
  if (typeof args === "string") {
    const match = /^\{"path":("(?:[^"\\]|\\.)*")/.exec(args);
    if (!match) return undefined;
    try {
      const path: unknown = JSON.parse(match[1]);
      return typeof path === "string" && path ? path : undefined;
    } catch {
      return undefined;
    }
  }
  if (!args || typeof args !== "object" || Array.isArray(args)) return undefined;
  const path = (args as Record<string, unknown>).path;
  return typeof path === "string" && path ? path : undefined;
}

function normalizePath(path: string): string {
  return path
    .replace(/\\/g, "/")
    .replace(/\/{2,}/g, "/")
    .replace(/(^|\/)(?:\.\/)+/g, "$1")
    .replace(/\/$/, "");
}

/**
 * Whether two paths may name the same file: equal, or one ends with the
 * other, since a call can give a workspace path either relative or absolute.
 * Errs toward a match, which only hides a snapshot.
 */
function mayBeSameFile(a: string, b: string): boolean {
  const left = normalizePath(a);
  const right = normalizePath(b);
  return left === right || left.endsWith(`/${right}`) || right.endsWith(`/${left}`);
}

/** Content a `write` call sent to the agent's workspace, as the chat holds it. */
export interface WrittenFile {
  /** The path the agent gave, shown to the user; never used to fetch anything. */
  path: string;
  fileName: string;
  /** What the call wrote; later edits or overwrites are not reflected. */
  content: string;
}

/**
 * The content an answer's finished `write` calls wrote, the latest per path.
 *
 * Only a write the chat saw finish, with its full arguments held, is offered.
 * Any later `edit` or `write` of the same path that was attempted hides the
 * earlier snapshot, as does a call still running when the turn ended, since
 * the file may have changed. When such a call's path is unknown (its stored
 * arguments were cut short), every earlier snapshot is hidden.
 */
export function writtenFiles(steps: readonly TraceStep[] | undefined): WrittenFile[] {
  let files: WrittenFile[] = [];
  const invalidate = (path: string | undefined) => {
    files = path ? files.filter((file) => !mayBeSameFile(file.path, path)) : [];
  };
  for (const step of steps ?? []) {
    if (step.kind !== "tool" || (step.tool !== "write" && step.tool !== "edit")) continue;
    // A cancelled call was never made, so it changed nothing.
    if (step.status === "cancelled") continue;
    invalidate(argsPath(step.args));
    if (step.tool !== "write" || step.status !== "done" || step.interrupted) continue;
    const args = step.args;
    if (!args || typeof args !== "object" || Array.isArray(args)) continue;
    const { path, content } = args as Record<string, unknown>;
    if (typeof path !== "string" || !path || typeof content !== "string") continue;
    files.push({ path, fileName: safeFileName(path), content });
  }
  return files;
}
