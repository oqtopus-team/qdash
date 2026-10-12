"use client";

import { MultiFileDiff } from "@pierre/diffs/react";

import { DARK_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";

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

  return (
    <MultiFileDiff
      newFile={{ contents: newContent, name: filename }}
      oldFile={{ contents: oldContent, name: filename }}
      options={{
        diffIndicators: "bars",
        diffStyle: layout,
        expandUnchanged: false,
        overflow: "wrap",
        themeType,
      }}
    />
  );
}
