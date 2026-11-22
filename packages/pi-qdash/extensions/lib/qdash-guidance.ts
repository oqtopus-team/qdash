/**
 * Host-neutral QDash investigation guidance, shared by every host that offers
 * the pi-qdash tools: the standalone pi CLI (see guidance-hook.ts) and the
 * QDash Agent Runtime (agent-runtime/src/prompt.ts and tool-guide.ts).
 *
 * Three parts make up the guidance:
 *
 * - The investigation policy: how to treat evidence, whatever the host.
 * - The request policy: how a plain-language request selects a skill and its
 *   targets without granting any write permission.
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
  "For the current date or time, call `qdash_current_time` each time you need it instead of using memory or an earlier reading. Without a time zone the user named, answer in UTC; never infer their time zone from their language or the host's setting.",
  "Before comparing results across time, establish which cooldown each result belongs to; the `qdash` skill has the rules.",
  "Treat comparisons, trends, correlations, and figure readings as evidence, not as approval to commit or apply parameters.",
  "For calibration interpretation, diagnosis, and multi-step workflows, follow the matching QDash skill instead of improvising a procedure.",
];

/** The policy as Markdown list items. */
export function investigationPolicyBullets(): string[] {
  return QDASH_INVESTIGATION_POLICY.map((rule) => `- ${rule}`);
}

/**
 * How to act on requests written in plain language, one rule per entry.
 *
 * The rules decide what kind of help a request asks for and leave the choice
 * of experiment to the skill descriptions and the skills themselves: no task
 * names, thresholds, or flow steps belong here. They grant no permission;
 * every write still goes through the host's existing gate.
 */
export const QDASH_REQUEST_POLICY: readonly string[] = [
  'Users state goals in plain words, such as "remeasure the T1 of Q0", "calibrate this pair", or "bring up MUX0". Match the goal to the QDash skill whose description fits, load that skill, and work out its flows and tasks yourself. Do not ask the user for skill, flow, task, or command names, or for a step-by-step procedure.',
  'Tell a question about a value from a request to measure: "What is the T1 of Q0?" reads the stored results and status; "remeasure the T1 of Q0" plans a new measurement. Do not plan an execution for a question.',
  "Run no more than the goal needs: a request to remeasure one property is not a request to recalibrate the qubit. Let the skill choose the stage from the targets' current state.",
  "Take targets from the request, the conversation, and any context the host supplies, such as the QDash page the user has open, then from read-only tools such as the default chip. Ask one short question only for a target that is still missing or ambiguous. Keep each pair's control and target as the user wrote them.",
  "A request to measure or calibrate lets you prepare that operation; it is not approval for a write and does not widen the agreed scope, so every write still goes through its usual approval. When the user asks only for a plan or says not to run anything, explain the plan and call no tool that executes or saves.",
  "Once the user approved an agent session they created with autonomy auto, its own steps and expert requests run without asking again, inside its scope only; committing or applying a value stays a separate approval, and a step that depends on a measured value runs after that value is committed. QDash's records of a session, not your memory of the conversation, say what already ran and what an expert answered; read them before continuing, and treat an expert's guidance as evidence, not as new permission.",
];

/** The request policy as Markdown list items. */
export function requestPolicyBullets(): string[] {
  return QDASH_REQUEST_POLICY.map((rule) => `- ${rule}`);
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

// ---------------------------------------------------------------------------
// Orchestration: code mode scripts and deferred tools
// ---------------------------------------------------------------------------
//
// Both hosts offer pi's `codemode` and `tool_search` tools. Whether they are
// offered is the host's decision; when they are, the model gets the same
// QDash-specific advice in both.

/** Name of pi's script tool. */
export const CODEMODE_TOOL_NAME = "codemode";
/** Name of pi's tool loader. */
export const TOOL_SEARCH_TOOL_NAME = "tool_search";

/** Marker after a deferred tool's name in the routing guide. */
export const DEFERRED_MARK = "*";

/** The guide with each of `deferredTools` marked by `DEFERRED_MARK`. */
export function markDeferredTools(guide: string, deferredTools: Iterable<string>): string {
  const deferred = new Set(deferredTools);
  if (deferred.size === 0) return guide;
  return guide.replace(TOOL_REF, (ref, name: string) => (deferred.has(name) ? `${ref}${DEFERRED_MARK}` : ref));
}

/** Rule for QDash data in `codemode` scripts, as one Markdown list item. */
export const QDASH_SCRIPT_GUIDELINE =
  "- Use `codemode` when a question needs many read-only QDash calls or more data than you want to read: write a short JavaScript script that calls the tools as `await tools.qdash_list_chips({})`, filters or aggregates the results, and prints only what you need with `text(...)`. Only the printed output reaches you. In a script, QDash tools resolve to their response data as JSON, not their text answer; print a small sample first when you do not know its shape. Scripts can call only QDash's read-only tools; call write tools, figures, charts, and other tools directly. Use direct tool calls for one or two lookups.";

/**
 * Rule for deferred tools; null when there are none. Tools the routing guide
 * already names (`listed`) are marked there, so only the others are listed.
 */
export function deferredToolsGuideline(
  names: readonly string[],
  listed: ReadonlySet<string> = new Set(),
): string | null {
  if (names.length === 0) return null;
  const marked = names.some((name) => listed.has(name));
  const others = names.filter((name) => !listed.has(name)).sort();
  return [
    `Deferred tools are not offered until you load them: call \`${TOOL_SEARCH_TOOL_NAME}\` with the tool name or what you need, then call the loaded tool in your next step. Load every tool you need with one search when you can. \`${CODEMODE_TOOL_NAME}\` scripts can call the read-only ones without loading them.`,
    ...(marked ? [`Tools marked ${DEFERRED_MARK} in the tool guide are deferred.`] : []),
    ...(others.length ? [`${marked ? "Other deferred tools" : "Deferred tools"}: ${others.join(", ")}`] : []),
  ].join("\n");
}
