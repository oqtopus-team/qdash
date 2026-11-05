/**
 * What a flow's code says it runs, read from the source in the editor: the task list and the
 * MUX targets the template declares at module level. It only reads the source; nothing here is
 * executed or rewritten, so a summary always matches what the user sees in the editor.
 *
 * Only the plain forms the templates use are recognized:
 *
 *     FAKE_CALIBRATION_TASKS: list[str] = ["FakeBringUp", "CheckRabi"]
 *     MUX_IDS: list[int] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
 *
 * Anything else, such as a computed list, gives null, and callers point the user at the code.
 */

export interface FlowCodeSummary {
  /** Task names in the order listed, or null when no task list was recognized. */
  tasks: string[] | null;
  /** MUX IDs, or null when no MUX target list was recognized. */
  muxIds: number[] | null;
}

const MAX_RANGE = 1024;

/** The right-hand side of a module-level `NAME[: type] = value` assignment, brackets balanced. */
function moduleAssignment(code: string, namePattern: RegExp): string | null {
  const lines = code.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const match = /^([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]+)?=\s*(.*)$/.exec(lines[index]);
    if (!match || !namePattern.test(match[1])) continue;
    let value = match[2];
    let depth = bracketDepth(value);
    while (depth > 0 && index + 1 < lines.length) {
      index += 1;
      value += `\n${lines[index]}`;
      depth = bracketDepth(value);
    }
    return depth === 0 ? value : null;
  }
  return null;
}

function stripComments(value: string): string {
  return value
    .split("\n")
    .map((line) => line.replace(/#.*$/, ""))
    .join("\n");
}

function bracketDepth(value: string): number {
  let depth = 0;
  for (const char of stripComments(value)) {
    if (char === "[" || char === "(") depth += 1;
    else if (char === "]" || char === ")") depth -= 1;
  }
  return depth;
}

function parseTasks(value: string): string[] | null {
  const body = /^\[([\s\S]*)\]$/.exec(stripComments(value).trim());
  if (!body) return null;
  const items = body[1]
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const tasks: string[] = [];
  for (const item of items) {
    const literal = /^(["'])([A-Za-z0-9_]+)\1$/.exec(item);
    if (!literal) return null;
    tasks.push(literal[2]);
  }
  return tasks.length > 0 ? tasks : null;
}

function parseMuxIds(value: string): number[] | null {
  const text = stripComments(value).trim();
  const range = /^list\(\s*range\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)\s*\)$/.exec(text);
  if (range) {
    const start = range[2] === undefined ? 0 : Number(range[1]);
    const stop = Number(range[2] ?? range[1]);
    if (stop - start > MAX_RANGE) return null;
    const ids: number[] = [];
    for (let id = start; id < stop; id += 1) ids.push(id);
    return ids;
  }
  const list = /^\[([\s\S]*)\]$/.exec(text);
  if (!list) return null;
  const items = list[1]
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!items.every((item) => /^\d+$/.test(item))) return null;
  return items.map(Number);
}

export function summarizeFlowCode(code: string): FlowCodeSummary {
  const tasksValue = moduleAssignment(code, /^[A-Z][A-Z0-9_]*_TASKS$/);
  const muxValue = moduleAssignment(code, /^MUX_IDS$/);
  return {
    tasks: tasksValue === null ? null : parseTasks(tasksValue),
    muxIds: muxValue === null ? null : parseMuxIds(muxValue),
  };
}

/** "MUX 0–15", "MUX 9, 15", or "MUX 0–3, 9" for a list of MUX IDs. */
export function formatMuxIds(ids: readonly number[]): string {
  const sorted = Array.from(new Set(ids)).sort((a, b) => a - b);
  const parts: string[] = [];
  let start = sorted[0];
  let previous = sorted[0];
  for (const id of [...sorted.slice(1), Number.NaN]) {
    if (id === previous + 1) {
      previous = id;
      continue;
    }
    parts.push(
      previous - start >= 2
        ? `${start}–${previous}`
        : start === previous
          ? `${start}`
          : `${start}, ${previous}`,
    );
    start = id;
    previous = id;
  }
  return sorted.length === 0 ? "no MUX" : `MUX ${parts.join(", ")}`;
}
