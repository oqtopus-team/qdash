/**
 * The Workflow editor's Explorer shows one creator's space as a file tree:
 * `<folder...>/<name>.py`. The directories are the flow's `folder` path and
 * the leaf is the flow. Dragging, dropping and renaming in that tree translate
 * to folder moves through `PATCH /flows/{name}/folder`; nothing else about a
 * flow changes, which is why only the folder segments are ever rewritten.
 */
import type { FlowSummary } from "@/schemas";

import { buildFlowTree, folderSegments, type FlowTreeNode } from "./flowFolders";

const FLOW_FILE_SUFFIX = ".py";

export interface FlowExplorerNode {
  path: string;
  type: "directory" | "file";
  children?: FlowExplorerNode[];
}

/** One folder change the API has to make. */
export interface FlowMove {
  name: string;
  folder: string;
}

/** A tree path split into what it means for a flow. */
export interface FlowTreeLocation {
  /** Folder path inside the space; "" at the top. */
  folder: string;
  /** The flow name for a file path, null for a directory. */
  name: string | null;
}

/** The creator a flow is filed under; flows without one share an "unknown" space. */
export function flowSpace(flow: Pick<FlowSummary, "created_by">): string {
  return flow.created_by || "unknown";
}

export function flowTreePath(flow: FlowSummary): string {
  return [...folderSegments(flow.folder), `${flow.name}${FLOW_FILE_SUFFIX}`].join("/");
}

/** Where a tree path points: a flow for a file path, a folder (or the top, "") for a directory. */
export function parseFlowTreePath(path: string | null | undefined): FlowTreeLocation {
  const segments = (path ?? "").split("/").filter(Boolean);
  const last = segments[segments.length - 1];
  if (last !== undefined && last.endsWith(FLOW_FILE_SUFFIX)) {
    return {
      folder: segments.slice(0, -1).join("/"),
      name: last.slice(0, -FLOW_FILE_SUFFIX.length),
    };
  }
  return { folder: segments.join("/"), name: null };
}

/**
 * The tree for one space. `emptyFolders` keeps folders the user made in this
 * session that hold no flow yet; the API only knows folders through flows.
 */
export function flowExplorerNodes(
  flows: readonly FlowSummary[],
  emptyFolders: readonly string[] = [],
): FlowExplorerNode[] {
  const toNodes = (node: FlowTreeNode): FlowExplorerNode[] => [
    ...node.children.map((child) => ({
      path: child.path,
      type: "directory" as const,
      children: toNodes(child),
    })),
    ...node.flows.map((flow) => ({ path: flowTreePath(flow), type: "file" as const })),
  ];
  return toNodes(buildFlowTree(flows, emptyFolders));
}

/** Flows filed under a folder path, at any depth. */
function flowsUnder(flows: readonly FlowSummary[], folder: string): FlowSummary[] {
  return flows.filter((flow) => {
    const own = folderSegments(flow.folder).join("/");
    return folder === "" || own === folder || own.startsWith(`${folder}/`);
  });
}

/** The folder a flow lands in when its folder `from` becomes `to`. */
function rebase(folder: string, from: string, to: string): string {
  if (from === "") return [to, folder].filter(Boolean).join("/");
  if (folder === from) return to;
  return [to, folder.slice(from.length + 1)].filter(Boolean).join("/");
}

/**
 * The moves for dropping tree items onto a directory, or onto the top of the
 * space when `targetDirectory` is null. A file moves into the directory; a
 * folder moves under it with its contents. Dropping onto a file or a folder
 * into itself yields null; a move that would change nothing is left out.
 */
export function dropMoves(
  flows: readonly FlowSummary[],
  draggedPaths: readonly string[],
  targetDirectory: string | null,
): FlowMove[] | null {
  const target = parseFlowTreePath(targetDirectory);
  if (target.name !== null) return null;
  const moves: FlowMove[] = [];
  for (const path of draggedPaths) {
    const source = parseFlowTreePath(path);
    if (source.name !== null) {
      if (source.folder !== target.folder) moves.push({ name: source.name, folder: target.folder });
      continue;
    }
    if (source.folder === "") return null;
    const leaf = source.folder.split("/").pop()!;
    const destination = [target.folder, leaf].filter(Boolean).join("/");
    // Onto its own parent: already there. Into itself: impossible.
    if (destination === source.folder) continue;
    if (destination.startsWith(`${source.folder}/`)) return null;
    for (const flow of flowsUnder(flows, source.folder)) {
      moves.push({
        name: flow.name,
        folder: rebase(folderSegments(flow.folder).join("/"), source.folder, destination),
      });
    }
  }
  return moves;
}

/** The moves for renaming a folder in place: every flow under it follows. */
export function renameMoves(
  flows: readonly FlowSummary[],
  sourceDirectory: string,
  destinationDirectory: string,
): FlowMove[] | null {
  const from = parseFlowTreePath(sourceDirectory);
  const to = parseFlowTreePath(destinationDirectory);
  if (from.name !== null || to.name !== null || from.folder === "" || to.folder === "") return null;
  if (from.folder === to.folder) return [];
  return flowsUnder(flows, from.folder).map((flow) => ({
    name: flow.name,
    folder: rebase(folderSegments(flow.folder).join("/"), from.folder, to.folder),
  }));
}
