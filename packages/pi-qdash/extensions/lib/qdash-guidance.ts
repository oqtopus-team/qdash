/**
 * Host-neutral QDash investigation guidance, shared by every host that offers
 * the pi-qdash tools: the standalone pi CLI (see guidance-hook.ts) and the
 * QDash Agent Runtime (agent-runtime/src/prompt.ts and tool-guide.ts).
 *
 * Two parts make up the guidance:
 *
 * - The investigation policy: how to treat evidence, whatever the host.
 * - The tool routing guide: the "Preferred tools" section of the `qdash`
 *   skill, limited to the tools the host actually offers.
 *
 * Keep host behavior out of this module: how results are displayed, how write
 * approval is asked for, how skills are read, and which orchestration tools
 * exist differ between hosts and belong to each host's own prompt. Keep
 * calibration interpretation and runbooks in the skills.
 *
 * The module has no runtime dependencies so either host can import it.
 */

/** The skill whose "Preferred tools" section is the routing guide. */
export const QDASH_GUIDANCE_SKILL = "qdash";

/** Investigation and evidence rules every host gives the model, one rule per entry. */
export const QDASH_INVESTIGATION_POLICY: readonly string[] = [
  "Every QDash fact must come from a tool result or from the user. Do not fill gaps from memory.",
  "Quote concrete values with units and say which chip, qubit, and execution they came from.",
  "When data is missing or a tool fails, say so plainly instead of guessing.",
  "Before comparing results across time, establish which cooldown each result belongs to; the `qdash` skill has the rules.",
  "Treat comparisons, trends, correlations, and figure readings as evidence, not as approval to commit or apply parameters.",
  "For calibration interpretation, diagnosis, and multi-step workflows, follow the matching QDash skill instead of improvising a procedure.",
];

/** The policy as Markdown list items. */
export function investigationPolicyBullets(): string[] {
  return QDASH_INVESTIGATION_POLICY.map((rule) => `- ${rule}`);
}

const SECTION_HEADING = /^## preferred tools\s*$/i;
const TOOL_REF = /`(qdash_[a-z0-9_]+)`/g;

/** The QDash tool names a guide mentions. */
export function toolRoutingNames(guide: string | null): Set<string> {
  return new Set(guide ? [...guide.matchAll(TOOL_REF)].map((m) => m[1]) : []);
}

/**
 * The "Preferred tools" section of the `qdash` skill, limited to
 * `availableTools`, or null when the section is missing or nothing is left.
 *
 * A guide that names a tool the model cannot call just invites a failed call,
 * so unavailable tools are removed: a bare list of names keeps the available
 * ones, a line that explains a tool goes as a whole, and list items whose
 * nested items were all removed go too.
 */
export function extractToolRouting(skillMarkdown: string, availableTools: Iterable<string>): string | null {
  const enabled = new Set(availableTools);
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
