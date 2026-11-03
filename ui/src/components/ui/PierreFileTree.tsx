"use client";

import type {
  ContextMenuItem,
  ContextMenuOpenContext,
  FileTree as FileTreeModel,
  FileTreeDragAndDropConfig,
  FileTreeInitialExpansion,
  FileTreeRenamingConfig,
  FileTreeSortComparator,
  GitStatusEntry,
} from "@pierre/trees";
import { FileTree, useFileTree } from "@pierre/trees/react";
import { useEffect, useMemo, useRef, type CSSProperties, type ReactNode } from "react";

import { DARK_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";

export interface PierreFileTreeNode {
  children?: PierreFileTreeNode[] | null;
  decoration?: {
    color?: string;
    text: string;
    title?: string;
  };
  path: string;
  type: string;
}

export type PierreFileTreeContextMenuRenderer = (
  item: ContextMenuItem,
  context: ContextMenuOpenContext,
  model: FileTreeModel,
) => ReactNode;

interface PierreFileTreeProps {
  nodes: PierreFileTreeNode[];
  onSelectFile: (path: string) => void;
  selectedPath?: string | null;
  /** Git state per path; files and their folders are tinted and badged like an IDE. */
  gitStatus?: readonly GitStatusEntry[];
  /** Fold `a/b/c` into one row when `a` and `b` hold nothing else. Default true. */
  flattenEmptyDirectories?: boolean;
  /** How deep the tree opens at first. Default 1. */
  initialExpansion?: FileTreeInitialExpansion;
  sort?: FileTreeSortComparator;
  /** Lets rows be dragged onto directories; the callbacks see canonical paths. */
  dragAndDrop?: FileTreeDragAndDropConfig;
  /** Lets rows be renamed in place (F2, or `model.startRenaming`). */
  renaming?: FileTreeRenamingConfig;
  /** A right-click menu for a row; the model is passed so the menu can mutate the tree. */
  renderContextMenu?: PierreFileTreeContextMenuRenderer;
  /**
   * Changing this value reloads the tree from `nodes` even when they did not
   * change: the way to undo a drag or rename the tree applied by itself.
   */
  resetToken?: number;
}

function collectTreePaths(nodes: PierreFileTreeNode[]): {
  decorations: Map<string, NonNullable<PierreFileTreeNode["decoration"]>>;
  files: Set<string>;
  directories: string[];
  paths: string[];
} {
  const decorations = new Map<string, NonNullable<PierreFileTreeNode["decoration"]>>();
  const files = new Set<string>();
  const directories: string[] = [];
  const paths: string[] = [];

  const visit = (items: PierreFileTreeNode[]) => {
    for (const item of items) {
      const path = item.type === "directory" ? `${item.path.replace(/\/$/, "")}/` : item.path;
      paths.push(path);
      if (item.type === "file") files.add(item.path);
      else directories.push(item.path.replace(/\/$/, ""));
      if (item.decoration) decorations.set(item.path, item.decoration);
      if (item.children) visit(item.children);
    }
  };

  visit(nodes);
  return { decorations, files, directories, paths };
}

/** The directories that contain a path, outermost first. */
function ancestors(path: string): string[] {
  const segments = path.split("/").filter(Boolean).slice(0, -1);
  return segments.map((_, index) => segments.slice(0, index + 1).join("/"));
}

/**
 * A themed `@pierre/trees` file tree. The model lives for the component's
 * life: when `nodes` change, the paths are swapped in and the folders that
 * were open stay open, so a reload after an edit does not fold the tree.
 */
export function PierreFileTree({
  nodes,
  onSelectFile,
  selectedPath,
  gitStatus,
  flattenEmptyDirectories = true,
  initialExpansion = 1,
  sort,
  dragAndDrop,
  renaming,
  renderContextMenu,
  resetToken = 0,
}: PierreFileTreeProps) {
  const { theme } = useTheme();
  const isDarkTheme = DARK_THEMES.includes(theme);
  const tree = useMemo(() => collectTreePaths(nodes), [nodes]);
  const pathsKey = tree.paths.join("\0");
  // The model reads callbacks once at creation; refs keep them current.
  const treeRef = useRef(tree);
  const onSelectFileRef = useRef(onSelectFile);
  const dragAndDropRef = useRef(dragAndDrop);
  const renamingRef = useRef(renaming);
  treeRef.current = tree;
  onSelectFileRef.current = onSelectFile;
  dragAndDropRef.current = dragAndDrop;
  renamingRef.current = renaming;

  const { model } = useFileTree({
    flattenEmptyDirectories,
    gitStatus,
    initialExpansion,
    initialSelectedPaths: selectedPath ? [selectedPath] : [],
    onSelectionChange: (selectedPaths) => {
      const selectedFile = Array.from(selectedPaths)
        .reverse()
        .find((path) => treeRef.current.files.has(path));
      if (selectedFile) onSelectFileRef.current(selectedFile);
    },
    paths: tree.paths,
    renderRowDecoration: ({ item }) => treeRef.current.decorations.get(item.path) ?? null,
    search: true,
    ...(sort ? { sort } : {}),
    ...(dragAndDrop
      ? {
          dragAndDrop: {
            canDrag: (dragged) => dragAndDropRef.current?.canDrag?.(dragged) ?? true,
            canDrop: (event) => dragAndDropRef.current?.canDrop?.(event) ?? true,
            onDropComplete: (event) => dragAndDropRef.current?.onDropComplete?.(event),
            onDropError: (error, event) => dragAndDropRef.current?.onDropError?.(error, event),
          } satisfies FileTreeDragAndDropConfig,
        }
      : {}),
    ...(renaming
      ? {
          renaming: {
            canRename: (item) => renamingRef.current?.canRename?.(item) ?? true,
            onRename: (event) => renamingRef.current?.onRename?.(event),
            onError: (error) => renamingRef.current?.onError?.(error),
          } satisfies FileTreeRenamingConfig,
        }
      : {}),
  });

  // Swap the paths in place of remounting; keep open what was open, and open
  // the way to the selected file so it is never hidden after a reload.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const open = new Set<string>();
    for (const directory of treeRef.current.directories) {
      const item = model.getItem(directory);
      if (item && "isExpanded" in item && item.isExpanded()) open.add(directory);
    }
    if (selectedPath) for (const directory of ancestors(selectedPath)) open.add(directory);
    model.resetPaths(treeRef.current.paths, { initialExpandedPaths: [...open] });
    // `selectedPath` is applied by the effect below; it must not trigger a reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, pathsKey, resetToken]);

  useEffect(() => {
    model.setGitStatus(gitStatus);
  }, [model, gitStatus]);

  useEffect(() => {
    if (!selectedPath || model.getSelectedPaths().includes(selectedPath)) return;

    for (const path of model.getSelectedPaths()) model.getItem(path)?.deselect();
    model.getItem(selectedPath)?.select();
  }, [model, selectedPath, pathsKey]);

  return (
    <FileTree
      aria-label="File explorer"
      className="block h-full min-h-0 w-full"
      model={model}
      renderContextMenu={
        renderContextMenu ? (item, context) => renderContextMenu(item, context, model) : undefined
      }
      style={
        {
          colorScheme: isDarkTheme ? "dark" : "light",
          "--trees-accent-override": "var(--color-primary)",
          "--trees-bg-muted-override": "var(--color-base-200)",
          "--trees-bg-override": "var(--color-base-100)",
          "--trees-border-color-override": "var(--color-base-300)",
          "--trees-fg-muted-override":
            "color-mix(in oklab, var(--color-base-content) 60%, transparent)",
          "--trees-fg-override": "var(--color-base-content)",
          "--trees-focus-ring-color-override": "var(--color-primary)",
          "--trees-input-bg-override": "var(--color-base-200)",
          "--trees-search-bg-override": "var(--color-base-200)",
          "--trees-search-fg-override": "var(--color-base-content)",
          "--trees-selected-bg-override":
            "color-mix(in oklab, var(--color-primary) 20%, var(--color-base-100))",
          "--trees-selected-fg-override": "var(--color-base-content)",
        } as CSSProperties
      }
    />
  );
}
