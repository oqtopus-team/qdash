"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { FolderInput, FolderPlus, Pencil } from "lucide-react";

import type { FlowSummary } from "@/schemas";

import { getListFlowsQueryKey, moveFlow } from "@/client/flow/flow";
import {
  PierreFileTree,
  type PierreFileTreeContextMenuRenderer,
  type PierreFileTreeNode,
} from "@/components/ui/PierreFileTree";
import { useToast } from "@/components/ui/Toast/useToast";
import {
  dropMoves,
  flowExplorerNodes,
  flowSpace,
  flowTreePath,
  parseFlowTreePath,
  renameMoves,
  type FlowMove,
} from "@/lib/flowExplorer";
import { buildFlowTree, folderPaths, normalizeFolderPath } from "@/lib/flowFolders";

interface FlowExplorerProps {
  flows: readonly FlowSummary[];
  /** The signed-in user, whose space is the default and is listed first. */
  username: string | null | undefined;
  /** The flow open in the editor, highlighted in the tree. */
  currentName: string;
  /** The open flow has unsaved changes. */
  isDirty: boolean;
  /** Text typed in the Filter box; only matching flow names are shown. */
  filter: string;
  /** The space to show first, when the page was opened for one; else the open flow's. */
  initialSpace?: string | null;
  onOpen: (name: string) => void;
}

/** The placeholder a new folder gets before the user names it. */
const NEW_FOLDER = "new_folder";
/** One shared empty list, so a space without pending folders is stable between renders. */
const NO_FOLDERS: readonly string[] = [];

function errorDetail(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return error instanceof Error ? error.message : "Unknown error";
}

/**
 * The editor's Explorer: one creator's space as `<folder>/<name>.py`, with a
 * selector to look at another creator's. Dragging a row onto a folder (or the
 * empty area for the top), renaming a folder, or picking a folder from a row's
 * menu re-files the flows through the move API.
 */
export function FlowExplorer({
  flows,
  username,
  currentName,
  isDirty,
  filter,
  initialSpace,
  onOpen,
}: FlowExplorerProps) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const spaces = useMemo(() => {
    const names = new Set(flows.map(flowSpace));
    if (username) names.add(username);
    return [...names].sort((a, b) => {
      if (a === username) return -1;
      if (b === username) return 1;
      return a.localeCompare(b);
    });
  }, [flows, username]);
  const current = flows.find((flow) => flow.name === currentName);
  const [chosenSpace, setSpace] = useState<string | null>(initialSpace ?? null);
  const space =
    chosenSpace && spaces.includes(chosenSpace)
      ? chosenSpace
      : current
        ? flowSpace(current)
        : (username ?? spaces[0] ?? "");
  const mine = space === username;

  // Folders made here that hold nothing yet; the API knows folders through flows.
  const [emptyFolders, setEmptyFolders] = useState<Map<string, string[]>>(new Map());
  const spaceFlows = useMemo(
    () => flows.filter((flow) => flowSpace(flow) === space),
    [flows, space],
  );
  const spaceEmptyFolders = emptyFolders.get(space) ?? NO_FOLDERS;

  // Undo what the tree did by itself when the server did not follow.
  const [resetToken, resetTree] = useReducer((n: number) => n + 1, 0);
  const refresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: getListFlowsQueryKey() });
    queryClient.invalidateQueries({ queryKey: ["flows"] });
  }, [queryClient]);

  const moveMutation = useMutation({
    mutationFn: async (moves: FlowMove[]) => {
      for (const move of moves) await moveFlow(move.name, { folder: move.folder });
      return moves;
    },
    onSuccess: (moves) => {
      refresh();
      if (moves.length === 1) {
        const [move] = moves;
        toast.success(`Moved ${move!.name} to ${move!.folder || "the top of the space"}`);
      } else {
        toast.success(`Moved ${moves.length} workflows`);
      }
    },
    onError: (error) => {
      refresh();
      resetTree();
      toast.error(`Could not move: ${errorDetail(error)}`);
    },
  });
  const busy = moveMutation.isPending;

  const addEmptyFolder = useCallback(
    (folder: string) => {
      if (folder === "") return;
      setEmptyFolders((map) => {
        const paths = map.get(space) ?? [];
        if (paths.includes(folder)) return map;
        return new Map(map).set(space, [...paths, folder]);
      });
    },
    [space],
  );
  const renameEmptyFolders = useCallback(
    (from: string, to: string) => {
      setEmptyFolders((map) => {
        const paths = map.get(space);
        if (!paths) return map;
        return new Map(map).set(
          space,
          paths.map((path) =>
            path === from
              ? to
              : path.startsWith(`${from}/`)
                ? `${to}${path.slice(from.length)}`
                : path,
          ),
        );
      });
    },
    [space],
  );
  // A folder that got a flow is known to the server; stop carrying it here.
  useEffect(() => {
    const known = new Set(folderPaths(buildFlowTree(spaceFlows)));
    if (!spaceEmptyFolders.some((path) => known.has(path))) return;
    setEmptyFolders((map) =>
      new Map(map).set(
        space,
        spaceEmptyFolders.filter((path) => !known.has(path)),
      ),
    );
  }, [space, spaceFlows, spaceEmptyFolders]);

  const needle = filter.trim().toLowerCase();
  const shown = useMemo(
    () =>
      needle ? spaceFlows.filter((flow) => flow.name.toLowerCase().includes(needle)) : spaceFlows,
    [spaceFlows, needle],
  );
  const nodes = useMemo<PierreFileTreeNode[]>(() => {
    const decorate = (node: PierreFileTreeNode): PierreFileTreeNode => {
      const location = node.type === "file" ? parseFlowTreePath(node.path) : null;
      const flow = location?.name ? shown.find((f) => f.name === location.name) : undefined;
      const decoration =
        flow && flow.name === currentName && isDirty
          ? { color: "var(--color-warning)", text: "●", title: "Unsaved changes" }
          : flow?.file_exists === false
            ? { color: "var(--color-warning)", text: "missing", title: "Missing source file" }
            : undefined;
      return {
        ...node,
        ...(decoration ? { decoration } : {}),
        children: node.children?.map(decorate),
      };
    };
    return flowExplorerNodes(shown, needle ? [] : spaceEmptyFolders).map(decorate);
  }, [shown, spaceEmptyFolders, needle, currentName, isDirty]);
  const selectedPath = current && flowSpace(current) === space ? flowTreePath(current) : null;
  const folders = useMemo(
    () => folderPaths(buildFlowTree(spaceFlows, spaceEmptyFolders)),
    [spaceFlows, spaceEmptyFolders],
  );

  const sort = useCallback(
    (left: { basename: string; isDirectory: boolean }, right: typeof left) => {
      if (left.isDirectory !== right.isDirectory) return left.isDirectory ? -1 : 1;
      return left.basename.localeCompare(right.basename);
    },
    [],
  );

  const renderContextMenu = useCallback<PierreFileTreeContextMenuRenderer>(
    (item, context, model) => {
      const location = parseFlowTreePath(item.path);
      if (item.kind === "directory") {
        return (
          <ul className="menu menu-sm w-52 rounded-box border border-base-300 bg-base-100 p-1 shadow-xl">
            <li>
              <button
                type="button"
                onClick={() => {
                  // A placeholder row the user names in place; cancelling removes it.
                  const placeholder = `${item.path}/${NEW_FOLDER}`;
                  model.add(`${placeholder}/`);
                  context.close({ restoreFocus: false });
                  model.startRenaming(placeholder, { removeIfCanceled: true });
                }}
              >
                <FolderPlus className="h-4 w-4" />
                New folder
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => {
                  context.close({ restoreFocus: false });
                  model.startRenaming(item.path);
                }}
              >
                <Pencil className="h-4 w-4" />
                Rename folder
              </button>
            </li>
          </ul>
        );
      }
      const name = location.name!;
      const targets = [
        { label: "Top of the space", folder: "" },
        ...folders.map((folder) => ({ label: folder, folder })),
      ];
      return (
        <ul className="menu menu-sm w-56 rounded-box border border-base-300 bg-base-100 p-1 shadow-xl">
          <li className="menu-title flex-row items-center gap-1">
            <FolderInput className="h-3.5 w-3.5" />
            Move {name} to
          </li>
          {targets.map((target) => (
            <li key={target.folder} className={target.folder === location.folder ? "disabled" : ""}>
              <button
                type="button"
                disabled={busy || target.folder === location.folder}
                onClick={() => {
                  context.close();
                  moveMutation.mutate([{ name, folder: target.folder }]);
                }}
              >
                {target.label}
              </button>
            </li>
          ))}
        </ul>
      );
    },
    [folders, busy, moveMutation],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-base-300 px-2 py-1">
        <label htmlFor="flow-explorer-space" className="sr-only">
          Space
        </label>
        <select
          id="flow-explorer-space"
          className="select select-ghost select-xs min-w-0 flex-1"
          value={space}
          onChange={(event) => setSpace(event.target.value)}
          title="Whose workflows to show"
        >
          {spaces.map((name) => (
            <option key={name} value={name}>
              {name === username ? `${name} (you)` : name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn-ghost btn-xs btn-square"
          title="New folder at the top of this space"
          aria-label="New folder"
          onClick={() => addEmptyFolder(nextNewFolderName(folders))}
        >
          <FolderPlus size={14} />
        </button>
      </div>
      {shown.length === 0 && spaceEmptyFolders.length === 0 ? (
        <div className="px-3 py-6 text-center text-xs text-base-content/40">
          {spaceFlows.length === 0
            ? mine
              ? "You have no flows yet."
              : `${space} has no flows.`
            : "No flows match the filter."}
        </div>
      ) : (
        <div className="min-h-0 flex-1">
          <PierreFileTree
            nodes={nodes}
            selectedPath={selectedPath}
            onSelectFile={(path) => {
              const { name } = parseFlowTreePath(path);
              if (name) onOpen(name);
            }}
            flattenEmptyDirectories={false}
            initialExpansion="open"
            sort={sort}
            resetToken={resetToken}
            dragAndDrop={{
              canDrag: () => !busy,
              canDrop: ({ draggedPaths, target }) =>
                dropMoves(spaceFlows, draggedPaths, target.directoryPath) !== null,
              onDropComplete: ({ draggedPaths, target }) => {
                const moves = dropMoves(spaceFlows, draggedPaths, target.directoryPath);
                if (moves && moves.length > 0) moveMutation.mutate(moves);
              },
              onDropError: (error) => toast.error(error),
            }}
            renaming={{
              canRename: (item) => item.isFolder,
              onRename: ({ sourcePath, destinationPath }) => {
                const from = parseFlowTreePath(sourcePath);
                const to = parseFlowTreePath(destinationPath);
                if (normalizeFolderPath(to.folder) !== to.folder || to.folder === "") {
                  toast.error("Folder names use letters, numbers and underscores");
                  resetTree();
                  return;
                }
                const moves = renameMoves(spaceFlows, sourcePath, destinationPath);
                if (moves === null) {
                  resetTree();
                  return;
                }
                renameEmptyFolders(from.folder, to.folder);
                if (moves.length === 0) addEmptyFolder(to.folder);
                else moveMutation.mutate(moves);
              },
              onError: (error) => toast.error(error),
            }}
            renderContextMenu={renderContextMenu}
          />
        </div>
      )}
    </div>
  );
}

/** `new_folder`, or `new_folder_2` and so on when that name is taken at the top. */
function nextNewFolderName(folders: readonly string[]): string {
  if (!folders.includes(NEW_FOLDER)) return NEW_FOLDER;
  let n = 2;
  while (folders.includes(`${NEW_FOLDER}_${n}`)) n += 1;
  return `${NEW_FOLDER}_${n}`;
}
