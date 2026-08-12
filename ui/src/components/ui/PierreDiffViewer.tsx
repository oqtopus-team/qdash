"use client";

import { MultiFileDiff } from "@pierre/diffs/react";

import { DARK_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";

interface PierreDiffViewerProps {
  filename: string;
  newContent: string;
  oldContent: string;
}

export function PierreDiffViewer({ filename, newContent, oldContent }: PierreDiffViewerProps) {
  const { theme } = useTheme();
  const themeType = DARK_THEMES.includes(theme) ? "dark" : "light";

  return (
    <MultiFileDiff
      newFile={{ contents: newContent, name: filename }}
      oldFile={{ contents: oldContent, name: filename }}
      options={{
        diffIndicators: "bars",
        diffStyle: "unified",
        expandUnchanged: false,
        overflow: "wrap",
        themeType,
      }}
    />
  );
}
