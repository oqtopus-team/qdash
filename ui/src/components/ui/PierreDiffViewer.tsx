"use client";

import { useMemo } from "react";
import type { FileContents, FileDiffOptions } from "@pierre/diffs";
import { MultiFileDiff } from "@pierre/diffs/react";

import { DARK_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";
import { useDiffHighlighter } from "@/lib/diffHighlighter";

interface PierreDiffViewerProps {
  filename: string;
  newContent: string;
  oldContent: string;
  layout?: "unified" | "split";
}

export function PierreDiffViewer({
  filename,
  newContent,
  oldContent,
  layout = "unified",
}: PierreDiffViewerProps) {
  const { theme } = useTheme();
  const themeType = DARK_THEMES.includes(theme) ? "dark" : "light";
  const preferredHighlighter = useDiffHighlighter();

  // The viewer compares these by reference, so keep them stable across renders.
  const oldFile = useMemo<FileContents>(
    () => ({ contents: oldContent, name: filename }),
    [oldContent, filename],
  );
  const newFile = useMemo<FileContents>(
    () => ({ contents: newContent, name: filename }),
    [newContent, filename],
  );
  const options = useMemo<FileDiffOptions<undefined, undefined>>(
    () => ({
      diffIndicators: "bars",
      diffStyle: layout,
      expandUnchanged: false,
      overflow: "wrap",
      themeType,
      preferredHighlighter: preferredHighlighter ?? "shiki-js",
    }),
    [layout, themeType, preferredHighlighter],
  );

  if (preferredHighlighter === null) return <div role="status">Loading diff…</div>;

  return (
    <MultiFileDiff
      // A fallback to another highlighter takes a fresh viewer.
      key={preferredHighlighter}
      newFile={newFile}
      oldFile={oldFile}
      options={options}
    />
  );
}
