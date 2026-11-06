/**
 * Tool routing guide taken from the pi-qdash `qdash` skill.
 *
 * The skill's "Preferred tools" section says which tool answers which kind of
 * question. In interactive pi the model reads the skill on demand; here the
 * section goes straight into the system prompt, because a small local model
 * picks better among sixty tools when the guide is in front of it. The rest of
 * the skill (cooldown rules, timeseries comparison) stays behind `read_skill`.
 *
 * Only tools the runtime actually exposes are kept: the allowlist and the
 * write-tools switch drop some pi-qdash tools, and a guide that names a tool
 * the model cannot call just invites a failed call.
 */

export const TOOL_GUIDE_SKILL = "qdash";
const SECTION_HEADING = /^## preferred tools\s*$/i;
const TOOL_REF = /`(qdash_[a-z0-9_]+)`/g;

/** The "Preferred tools" section of the skill, limited to `enabledTools`, or null. */
export function extractToolGuide(
  skillMarkdown: string,
  enabledTools: Iterable<string>,
): string | null {
  const enabled = new Set(enabledTools);
  const lines = skillMarkdown.split("\n");
  const start = lines.findIndex((line) => SECTION_HEADING.test(line));
  if (start === -1) return null;
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (/^##\s/.test(lines[i])) {
      end = i;
      break;
    }
  }

  const kept: string[] = [];
  for (const line of lines.slice(start + 1, end)) {
    const refs = [...line.matchAll(TOOL_REF)].map((m) => m[1]);
    if (refs.length === 0) {
      kept.push(line);
      continue;
    }
    const missing = refs.filter((name) => !enabled.has(name));
    if (missing.length === 0) {
      kept.push(line);
      continue;
    }
    // A bare list of names keeps the available ones. A line that explains a
    // tool ("`x`, then `y` for ...") reads wrong with a name cut out, so it
    // goes as a whole when any of its tools is unavailable.
    if (missing.length === refs.length || !isBareToolList(line)) continue;
    let text = line;
    for (const name of missing) text = text.replace(new RegExp(`\`${name}\`,?\\s*`), "");
    kept.push(text.replace(/,\s*$/, "").replace(/,\s*,/g, ","));
  }

  const body = dropEmptyParents(kept).join("\n").trim();
  return body ? body : null;
}

/** "- `a`, `b`, `c`": a list marker and backticked tool names, nothing else. */
function isBareToolList(line: string): boolean {
  return /^\s*(?:(?:\d+\.|-)\s+)?(?:`qdash_[a-z0-9_]+`\s*,?\s*)+$/.test(line);
}

/** Remove list items whose nested items were all dropped (e.g. "5. Use `x` for:"). */
function dropEmptyParents(lines: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const parentWithChildren = /^\s*(\d+\.|-)\s.*:\s*$/.test(line);
    if (parentWithChildren) {
      const indent = line.match(/^\s*/)![0].length;
      const next = lines[i + 1];
      const hasChild = next !== undefined && next.match(/^\s*/)![0].length > indent && next.trim();
      if (!hasChild) continue;
    }
    out.push(line);
  }
  return out;
}
