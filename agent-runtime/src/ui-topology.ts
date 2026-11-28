// See ui-tool.ts for why this path resolves in the image too.
import { UI_SPEC_LIMITS } from "../../ui/src/lib/agentUiSpec.ts";

/**
 * Repairs to the tree shape of a `render_ui` spec that have exactly one safe
 * reading, applied by the runtime before the shared, strict `validateUiSpec`.
 * The stored spec and the chat's own validation stay strict; only the model's
 * call is repaired, and the repairs are reported back to the model.
 *
 * Applied, in order:
 * 1. A container that lists the same child more than once keeps the first.
 * 2. An element listed both by a container and by a descendant of that
 *    container keeps only the nearest parent (`s -> t` is dropped when
 *    `s -> f -> t` exists), since the descendant path already places it.
 * 3. Elements no container lists (orphans, with their subtrees) are kept, in
 *    element order: appended to a vertical Stack root, or else the root and
 *    the orphans are wrapped in a new vertical Stack with an unused id.
 *
 * Anything else is left for validation to reject: missing ids, cycles, a
 * child of two unrelated containers, children on a leaf, a root with a
 * parent, invalid props, and every limit. The input is never modified.
 */

export interface UiTopologyResult {
  /** The repaired spec, or the input itself when nothing was repaired. */
  spec: unknown;
  /** One line per repair, for the model. */
  repairs: string[];
  /** Why the shape cannot be repaired, phrased for the model; empty when nothing blocked it. */
  problems: string[];
}

const CONTAINERS: ReadonlySet<string> = new Set(["Stack", "Card"]);
const WRAPPER_ID = "ui-root";

interface Node {
  type: string;
  children: string[];
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function list(ids: readonly string[]): string {
  return ids.map((id) => `"${id}"`).join(", ");
}

/** The element graph, or undefined when its shape is not one these repairs handle. */
function readGraph(spec: unknown): { root: string; nodes: Map<string, Node> } | undefined {
  if (!isPlainObject(spec) || typeof spec.root !== "string" || !isPlainObject(spec.elements)) {
    return undefined;
  }
  const ids = Object.keys(spec.elements);
  if (ids.length > UI_SPEC_LIMITS.maxElements) return undefined;
  const nodes = new Map<string, Node>();
  for (const id of ids) {
    const element = spec.elements[id];
    if (!isPlainObject(element) || typeof element.type !== "string") return undefined;
    const children = element.children ?? [];
    if (!Array.isArray(children) || children.some((child) => typeof child !== "string")) return undefined;
    if (children.length > 0 && !CONTAINERS.has(element.type)) return undefined;
    nodes.set(id, { type: element.type, children: children as string[] });
  }
  if (!nodes.has(spec.root)) return undefined;
  for (const node of nodes.values()) {
    if (node.children.some((child) => !nodes.has(child))) return undefined;
  }
  return { root: spec.root, nodes };
}

function hasCycle(nodes: Map<string, Node>): boolean {
  const state = new Map<string, "open" | "done">();
  const visit = (id: string): boolean => {
    const s = state.get(id);
    if (s === "open") return true;
    if (s === "done") return false;
    state.set(id, "open");
    for (const child of nodes.get(id)!.children) if (visit(child)) return true;
    state.set(id, "done");
    return false;
  };
  for (const id of nodes.keys()) if (visit(id)) return true;
  return false;
}

/** Ids reachable from `from` by one or more edges. */
function descendants(nodes: Map<string, Node>, from: string): Set<string> {
  const out = new Set<string>();
  const stack = [...nodes.get(from)!.children];
  while (stack.length > 0) {
    const id = stack.pop()!;
    if (out.has(id)) continue;
    out.add(id);
    stack.push(...nodes.get(id)!.children);
  }
  return out;
}

function unusedId(nodes: Map<string, Node>): string {
  if (!nodes.has(WRAPPER_ID)) return WRAPPER_ID;
  for (let n = 2; ; n++) {
    const id = `${WRAPPER_ID}-${n}`;
    if (!nodes.has(id)) return id;
  }
}

export function normalizeUiTopology(spec: unknown): UiTopologyResult {
  const unchanged = (problems: string[] = []): UiTopologyResult => ({ spec, repairs: [], problems });
  const graph = readGraph(spec);
  if (!graph) return unchanged();
  const { root } = graph;
  const repairs: string[] = [];

  // 1. Duplicate references within one container.
  const nodes = new Map<string, Node>();
  for (const [id, node] of graph.nodes) {
    const children = [...new Set(node.children)];
    const twice = node.children.filter((child, i) => node.children.indexOf(child) !== i);
    if (twice.length > 0) {
      repairs.push(`removed the repeated ${list([...new Set(twice)])} from "${id}".children`);
    }
    nodes.set(id, { type: node.type, children });
  }
  if (hasCycle(nodes)) return unchanged();

  const parentsOf = new Map<string, string[]>();
  for (const id of nodes.keys()) parentsOf.set(id, []);
  for (const [id, node] of nodes) for (const child of node.children) parentsOf.get(child)!.push(id);
  if (parentsOf.get(root)!.length > 0) {
    return unchanged([
      `the root "${root}" is listed as a child of ${list(parentsOf.get(root)!)}; the root has no parent`,
    ]);
  }

  // 2. Redundant ancestor references: keep only the nearest of nested parents.
  const reach = new Map<string, Set<string>>();
  const reachOf = (id: string) => {
    let r = reach.get(id);
    if (!r) reach.set(id, (r = descendants(nodes, id)));
    return r;
  };
  const drop = new Map<string, Set<string>>();
  const problems: string[] = [];
  for (const [child, parents] of parentsOf) {
    if (parents.length < 2) continue;
    const redundant = parents.filter((p) => parents.some((q) => q !== p && reachOf(p).has(q)));
    const kept = parents.filter((p) => !redundant.includes(p));
    if (kept.length > 1) {
      problems.push(
        `"${child}" is a child of both ${list(kept)}, and neither contains the other; list it under only one of them`,
      );
      continue;
    }
    for (const p of redundant) {
      if (!drop.has(p)) drop.set(p, new Set());
      drop.get(p)!.add(child);
      repairs.push(`removed "${child}" from "${p}".children; it is already inside "${kept[0]}" there`);
    }
  }
  if (problems.length > 0) return unchanged(problems);
  for (const [p, children] of drop) {
    const node = nodes.get(p)!;
    node.children = node.children.filter((child) => !children.has(child));
    for (const child of children) parentsOf.set(child, parentsOf.get(child)!.filter((q) => q !== p));
  }

  // 3. Orphans: tops of the forest other than the root, in element order.
  const orphans = [...nodes.keys()].filter((id) => id !== root && parentsOf.get(id)!.length === 0);
  let newRoot = root;
  if (orphans.length > 0) {
    const top = nodes.get(root)!;
    const direction = (spec as { elements: Record<string, { props?: { direction?: unknown } }> })
      .elements[root].props?.direction;
    if (
      top.type === "Stack" &&
      (direction === undefined || direction === null || direction === "vertical") &&
      top.children.length + orphans.length <= UI_SPEC_LIMITS.maxChildren
    ) {
      top.children = [...top.children, ...orphans];
      repairs.push(`added the unplaced ${list(orphans)} to the end of the root stack "${root}"`);
    } else {
      newRoot = unusedId(nodes);
      nodes.set(newRoot, { type: "Stack", children: [root, ...orphans] });
      repairs.push(
        `wrapped the root "${root}" and the unplaced ${list(orphans)} in a new vertical stack "${newRoot}"`,
      );
    }
  }

  if (repairs.length === 0) return unchanged();
  const source = (spec as { elements: Record<string, Record<string, unknown>> }).elements;
  // fromEntries defines own properties, so no id can reach a prototype.
  const elements = Object.fromEntries(
    [...nodes].map(([id, node]) => [
      id,
      Object.hasOwn(source, id)
        ? { ...source[id], children: node.children }
        : { type: "Stack", props: { direction: "vertical" }, children: node.children },
    ]),
  );
  return { spec: { ...(spec as Record<string, unknown>), root: newRoot, elements }, repairs, problems: [] };
}
