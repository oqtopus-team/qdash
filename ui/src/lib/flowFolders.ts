/**
 * The workflow list is shown as one folder per creator. The signed-in user's
 * folder comes first so their own flows are never below someone else's; the
 * other folders follow in name order, and flows keep the order the API gave.
 *
 * Inside a creator's folder, each flow's `folder` path ("daily/t1") places it
 * in a nested subfolder; flows without one sit at the creator's root.
 */
import type { FlowSummary } from "@/schemas";

export interface FlowTreeNode {
  /** The last path segment; "" at the creator's root. */
  name: string;
  /** The full folder path, "" at the creator's root. */
  path: string;
  /** Flows placed directly in this folder. */
  flows: FlowSummary[];
  /** Subfolders in name order. */
  children: FlowTreeNode[];
}

export interface FlowFolder {
  /** The creator's username, which names the folder. */
  creator: string;
  /** Whether the folder belongs to the signed-in user. */
  mine: boolean;
  /** Every flow of this creator, in API order. */
  flows: FlowSummary[];
  /** The same flows arranged by their `folder` paths. */
  root: FlowTreeNode;
}

/**
 * Group flows by creator. `emptyFolders` maps a creator to folder paths that
 * should exist even while no flow is in them: folders the user has just made
 * in the browser and not yet moved anything into.
 */
export function groupFlowsByCreator(
  flows: readonly FlowSummary[],
  username: string | null | undefined,
  emptyFolders: ReadonlyMap<string, readonly string[]> = new Map(),
): FlowFolder[] {
  const byCreator = new Map<string, FlowSummary[]>();
  for (const flow of flows) {
    const creator = flow.created_by || "unknown";
    const group = byCreator.get(creator);
    if (group) group.push(flow);
    else byCreator.set(creator, [flow]);
  }
  for (const creator of emptyFolders.keys()) {
    if (!byCreator.has(creator)) byCreator.set(creator, []);
  }
  return [...byCreator.entries()]
    .map(([creator, group]) => ({
      creator,
      mine: creator === username,
      flows: group,
      root: buildFlowTree(group, emptyFolders.get(creator) ?? []),
    }))
    .sort((a, b) => {
      if (a.mine !== b.mine) return a.mine ? -1 : 1;
      return a.creator.localeCompare(b.creator);
    });
}

/** The segments of a folder path; blank or malformed values mean the root. */
export function folderSegments(folder: string | undefined): string[] {
  return (folder ?? "").split("/").filter((segment) => segment.trim() !== "");
}

const SEGMENT = /^[A-Za-z0-9_]+$/;

/**
 * The canonical form of a folder path typed by the user, or null when a
 * segment holds characters the API would refuse. "" is the root. Mirrors
 * `FlowService._normalize_folder` so the page can reject input before a request.
 */
export function normalizeFolderPath(input: string): string | null {
  const segments = folderSegments(input.trim());
  if (segments.some((segment) => !SEGMENT.test(segment))) return null;
  return segments.join("/");
}

export function buildFlowTree(
  flows: readonly FlowSummary[],
  emptyFolders: readonly string[] = [],
): FlowTreeNode {
  const root: FlowTreeNode = { name: "", path: "", flows: [], children: [] };
  const nodeAt = (folder: string | undefined): FlowTreeNode => {
    let node = root;
    for (const segment of folderSegments(folder)) {
      let child = node.children.find((c) => c.name === segment);
      if (!child) {
        child = {
          name: segment,
          path: node.path ? `${node.path}/${segment}` : segment,
          flows: [],
          children: [],
        };
        node.children.push(child);
      }
      node = child;
    }
    return node;
  };
  for (const flow of flows) nodeAt(flow.folder).flows.push(flow);
  for (const folder of emptyFolders) nodeAt(folder);
  sortChildren(root);
  return root;
}

/** Every folder path under a node, depth first, in display order. */
export function folderPaths(node: FlowTreeNode): string[] {
  return node.children.flatMap((child) => [child.path, ...folderPaths(child)]);
}

export function countFlows(node: FlowTreeNode): number {
  return node.flows.length + node.children.reduce((sum, child) => sum + countFlows(child), 0);
}

function sortChildren(node: FlowTreeNode): void {
  node.children.sort((a, b) => a.name.localeCompare(b.name));
  for (const child of node.children) sortChildren(child);
}
