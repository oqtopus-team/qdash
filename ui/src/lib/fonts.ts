import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

// Font-family strings for libraries that render outside the CSS cascade
// (Monaco measures glyphs itself; Plotly writes font names into SVG).
export const sansFontFamily = `${GeistSans.style.fontFamily}, ui-sans-serif, system-ui, sans-serif`;
export const monoFontFamily = `${GeistMono.style.fontFamily}, ui-monospace, SFMono-Regular, Menlo, monospace`;
