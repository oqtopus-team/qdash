import type { Monaco } from "@monaco-editor/react";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

// Font-family strings for libraries that render outside the CSS cascade
// (Monaco measures glyphs itself; Plotly writes font names into SVG).
export const sansFontFamily = `${GeistSans.style.fontFamily}, ui-sans-serif, system-ui, sans-serif`;
export const monoFontFamily = `${GeistMono.style.fontFamily}, ui-monospace, SFMono-Regular, Menlo, monospace`;

/**
 * Monaco measures glyph widths when an editor mounts. A self-hosted font can still be loading at
 * that moment, so the editor keeps fallback metrics and the caret drifts. Call this from onMount.
 */
export function remeasureMonacoFontsWhenLoaded(monaco: Pick<Monaco, "editor">): void {
  if (typeof document === "undefined" || !("fonts" in document)) return;
  const remeasure = () => monaco.editor.remeasureFonts();
  void document.fonts.load(`14px ${GeistMono.style.fontFamily}`).then(remeasure, remeasure);
}
