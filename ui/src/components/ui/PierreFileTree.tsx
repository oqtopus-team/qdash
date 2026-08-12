"use client";

import { FileTree, useFileTree } from "@pierre/trees/react";
import { useEffect, useMemo, useRef, type CSSProperties } from "react";

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

interface PierreFileTreeProps {
  nodes: PierreFileTreeNode[];
  onSelectFile: (path: string) => void;
  selectedPath?: string | null;
}

function collectTreePaths(nodes: PierreFileTreeNode[]): {
  decorations: Map<string, NonNullable<PierreFileTreeNode["decoration"]>>;
  files: Set<string>;
  paths: string[];
} {
  const decorations = new Map<string, NonNullable<PierreFileTreeNode["decoration"]>>();
  const files = new Set<string>();
  const paths: string[] = [];

  const visit = (items: PierreFileTreeNode[]) => {
    for (const item of items) {
      const path = item.type === "directory" ? `${item.path.replace(/\/$/, "")}/` : item.path;
      paths.push(path);
      if (item.type === "file") files.add(item.path);
      if (item.decoration) decorations.set(item.path, item.decoration);
      if (item.children) visit(item.children);
    }
  };

  visit(nodes);
  return { decorations, files, paths };
}

function PierreFileTreeInstance({ nodes, onSelectFile, selectedPath }: PierreFileTreeProps) {
  const { theme } = useTheme();
  const isDarkTheme = DARK_THEMES.includes(theme);
  const { decorations, files, paths } = useMemo(() => collectTreePaths(nodes), [nodes]);
  const onSelectFileRef = useRef(onSelectFile);
  const decorationsRef = useRef(decorations);
  onSelectFileRef.current = onSelectFile;
  decorationsRef.current = decorations;

  const { model } = useFileTree({
    flattenEmptyDirectories: true,
    initialExpansion: 1,
    initialSelectedPaths: selectedPath ? [selectedPath] : [],
    onSelectionChange: (selectedPaths) => {
      const selectedFile = Array.from(selectedPaths)
        .reverse()
        .find((path) => files.has(path));
      if (selectedFile) onSelectFileRef.current(selectedFile);
    },
    paths,
    renderRowDecoration: ({ item }) => decorationsRef.current.get(item.path) ?? null,
    search: true,
  });

  useEffect(() => {
    if (!selectedPath || model.getSelectedPaths().includes(selectedPath)) return;

    for (const path of model.getSelectedPaths()) model.getItem(path)?.deselect();
    model.getItem(selectedPath)?.select();
  }, [model, selectedPath]);

  return (
    <FileTree
      aria-label="File explorer"
      className="block h-full min-h-0 w-full"
      model={model}
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

export function PierreFileTree(props: PierreFileTreeProps) {
  const treeKey = collectTreePaths(props.nodes).paths.join("\0");

  return <PierreFileTreeInstance key={treeKey} {...props} />;
}
