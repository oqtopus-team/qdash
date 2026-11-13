import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashClient } from "@oqtopus-team/qdash-client";
import { Type } from "typebox";

import { toTextToolResult } from "../lib/results.js";

type ConnectionParams = {
  profile?: string;
  configPath?: string;
  useEnv?: boolean;
};

type SearchParams = ConnectionParams & {
  query: string;
  root?: string;
  pathPrefix?: string;
  mode?: "content" | "path";
  caseSensitive?: boolean;
  limit?: number;
};

type ReadParams = ConnectionParams & {
  path: string;
  root?: string;
  startLine?: number;
  endLine?: number;
};

type SourceRoot = {
  name: string;
  kind: string;
  version?: string | null;
  revision?: string | null;
  revision_source?: string | null;
  dirty?: boolean | null;
};

type SourceRoots = {
  roots?: SourceRoot[];
  missing_dependencies?: string[];
  execution_revision_recorded?: boolean;
};

type SearchResult = {
  query: string;
  mode: string;
  matches?: Array<{ root: string; path: string; line?: number | null; text?: string | null }>;
  truncated?: boolean;
};

type SourceFile = {
  root: string;
  path: string;
  start_line: number;
  end_line: number;
  total_lines: number;
  content: string;
  truncated?: boolean;
  revision?: string | null;
};

export type SourceCodeDependencies = {
  makeClient(params: ConnectionParams): Promise<QDashClient>;
};

const connectionParams = {
  profile: Type.Optional(Type.String({ description: "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise 'default'." })),
  configPath: Type.Optional(Type.String({ description: "Optional path to qdash config.ini." })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

const REVISION_CAVEAT =
  "QDash does not record which revision an execution ran with, so this source cannot be shown to match a given execution.";

/** One line per root: its name, version and the revision when the server could establish it. */
export function describeRoot(root: SourceRoot): string {
  const version = root.version ? ` ${root.version}` : "";
  const revision = root.revision
    ? `revision ${root.revision} (from ${root.revision_source ?? "unknown source"})${root.dirty ? ", with uncommitted local changes" : ""}`
    : "revision unknown";
  return `- ${root.name} (${root.kind}${version}): ${revision}`;
}

export function sourceRootsMarkdown(data: SourceRoots): string {
  const roots = data.roots ?? [];
  const lines = roots.length
    ? ["Readable source roots:", ...roots.map(describeRoot)]
    : ["No source is available on this QDash server; the code cannot be read."];
  if (data.missing_dependencies?.length) {
    lines.push("", `Not available here: ${data.missing_dependencies.join(", ")}.`);
  }
  if (!data.execution_revision_recorded) lines.push("", REVISION_CAVEAT);
  return lines.join("\n");
}

export function searchMarkdown(data: SearchResult): string {
  const matches = data.matches ?? [];
  if (!matches.length) {
    if (data.truncated) {
      return `No matches found in the files searched for \`${data.query}\`. The search stopped at the file limit; unsearched files may match. Narrow root or pathPrefix.`;
    }
    return `No ${data.mode === "path" ? "file paths" : "lines"} match \`${data.query}\`.`;
  }
  const lines = matches.map((match) =>
    match.line == null ? `- ${match.root}:${match.path}` : `- ${match.root}:${match.path}:${match.line}  ${match.text ?? ""}`,
  );
  if (data.truncated) lines.push("", "Results stopped at the limit; narrow the query, root or pathPrefix.");
  return lines.join("\n");
}

export function fileMarkdown(data: SourceFile): string {
  const header = `${data.root}:${data.path} lines ${data.start_line}-${data.end_line} of ${data.total_lines}`
    + (data.revision ? ` (revision ${data.revision})` : " (revision unknown)");
  const more = data.truncated ? `\n\nMore lines follow; read from line ${data.end_line + 1}.` : "";
  return `${header}\n\n${data.content}${more}`;
}

/** A refusal or a missing file is something the model reports, not a failed turn. */
function sourceRefusal(error: unknown): string | undefined {
  if (!error || typeof error !== "object") return undefined;
  const value = error as { status?: unknown; statusCode?: unknown; response?: { status?: unknown }; message?: unknown };
  const status = Number(value.status ?? value.statusCode ?? value.response?.status);
  if (![400, 403, 404, 413].includes(status)) return undefined;
  const message = String(value.message ?? `HTTP ${status}`);
  // A bare FastAPI-style 404 can indicate an unavailable route or proxy mismatch.
  if (status === 404 && /:\s*Not Found$/.test(message)) {
    return `${message}. The /copilot/source endpoint may be unavailable. Check API routing/proxy configuration and update the API image if it predates source access.`;
  }
  return message;
}

export function registerSourceCodeTools(pi: Pick<ExtensionAPI, "registerTool">, deps: SourceCodeDependencies): void {
  pi.registerTool({
    name: "qdash_list_source_roots",
    label: "QDash Source Roots",
    description: "List the QDash and dependency source trees this server can read, with their versions and revisions.",
    promptSnippet: "See which source code can be read and at which revision",
    promptGuidelines: [
      "Call qdash_list_source_roots before citing code when the available roots or revisions are not already stated.",
      "Never claim that served source matches an execution's code; QDash does not record the revision an execution ran with.",
    ],
    parameters: Type.Object(connectionParams),
    async execute(_toolCallId, params: ConnectionParams) {
      const client = await deps.makeClient(params);
      const data = await client.listSourceRoots() as SourceRoots;
      return toTextToolResult(sourceRootsMarkdown(data), data, { roots: (data.roots ?? []).map((root) => root.name) });
    },
  });

  pi.registerTool({
    name: "qdash_search_source",
    label: "QDash Search Source",
    description: "Search QDash and dependency source code read-only: literal text in file contents, or file names with mode 'path'.",
    promptSnippet: "Find where an error, function or task is defined in QDash or qubex source",
    promptGuidelines: [
      "Use qdash_search_source with an exception message, function or class name from a traceback to locate the code behind a failure.",
      "Search for literal text, not a regular expression; narrow with root and pathPrefix (for example workflow/calibtasks).",
    ],
    parameters: Type.Object({
      ...connectionParams,
      query: Type.String({ description: "Literal text to find, at most 200 characters." }),
      root: Type.Optional(Type.String({ description: "Source root such as qdash or qubex; all roots when omitted." })),
      pathPrefix: Type.Optional(Type.String({ description: "Directory or file inside the root to search, such as workflow/engine." })),
      mode: Type.Optional(Type.Union([Type.Literal("content"), Type.Literal("path")], { description: "content (default) searches lines; path searches file paths." })),
      caseSensitive: Type.Optional(Type.Boolean({ description: "Match case exactly. Defaults to false." })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 200, description: "Maximum matches, default 50." })),
    }),
    async execute(_toolCallId, params: SearchParams) {
      const client = await deps.makeClient(params);
      try {
        const data = await client.searchSource({
          query: params.query,
          root: params.root,
          pathPrefix: params.pathPrefix,
          mode: params.mode,
          caseSensitive: params.caseSensitive,
          limit: params.limit,
        }) as SearchResult;
        return toTextToolResult(searchMarkdown(data), data, { query: params.query, matches: data.matches?.length ?? 0 });
      } catch (error) {
        const refusal = sourceRefusal(error);
        if (!refusal) throw error;
        return toTextToolResult(`Source search refused: ${refusal}`, { error: refusal }, { query: params.query, matches: 0 });
      }
    },
  });

  pi.registerTool({
    name: "qdash_read_source",
    label: "QDash Read Source",
    description: "Read numbered lines of a QDash or dependency source file, read-only, up to 400 lines per call.",
    promptSnippet: "Read the code at a traceback frame or search hit",
    promptGuidelines: [
      "Pass a path as a traceback prints it (for example /app/qdash/workflow/engine/x.py) without root, or a path inside a root with root.",
      "Read a window around the line you need with startLine and endLine; cite code as root:path:line.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      path: Type.String({ description: "Path inside the root, or a traceback path when root is omitted." }),
      root: Type.Optional(Type.String({ description: "Source root such as qdash or qubex." })),
      startLine: Type.Optional(Type.Integer({ minimum: 1, description: "First line, default 1." })),
      endLine: Type.Optional(Type.Integer({ minimum: 1, description: "Last line; at most 400 lines are returned." })),
    }),
    async execute(_toolCallId, params: ReadParams) {
      const client = await deps.makeClient(params);
      try {
        const data = await client.getSourceFile({
          path: params.path,
          root: params.root,
          startLine: params.startLine,
          endLine: params.endLine,
        }) as SourceFile;
        return toTextToolResult(fileMarkdown(data), data, { root: data.root, path: data.path, startLine: data.start_line, endLine: data.end_line });
      } catch (error) {
        const refusal = sourceRefusal(error);
        if (!refusal) throw error;
        return toTextToolResult(`Source file unavailable: ${refusal}`, { error: refusal }, { path: params.path });
      }
    },
  });
}
