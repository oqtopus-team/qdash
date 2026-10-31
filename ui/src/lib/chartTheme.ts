import type { Layout } from "plotly.js";

import { sansFontFamily } from "@/lib/fonts";

/**
 * One palette for every Plotly chart. The brand indigo leads; the other series colors are muted
 * hues chosen to stay apart from each other and from the status colors, which are reserved for
 * pass/fail meaning. Chrome around the chart (grid, ticks, legend) comes from the neutral ramp.
 */
export interface ChartTheme {
  text: string;
  muted: string;
  grid: string;
  accent: string;
  secondary: string;
  series: readonly string[];
  pass: string;
  fail: string;
  warn: string;
}

const LIGHT: ChartTheme = {
  text: "#3c3c43",
  muted: "rgba(60, 60, 67, 0.6)",
  grid: "rgba(60, 60, 67, 0.1)",
  accent: "#1f1fdd",
  secondary: "#b45309",
  series: [
    "#1f1fdd",
    "#b45309",
    "#0f766e",
    "#9d174d",
    "#0e7490",
    "#6d28d9",
    "#a16207",
    "#be123c",
    "#475569",
    "#15803d",
  ],
  pass: "#16a34a",
  fail: "#dc2626",
  warn: "#d97706",
};

const DARK: ChartTheme = {
  text: "#e5e5e7",
  muted: "rgba(229, 229, 231, 0.6)",
  grid: "rgba(229, 229, 231, 0.1)",
  accent: "#7b7bf7",
  secondary: "#fbbf24",
  series: [
    "#7b7bf7",
    "#fbbf24",
    "#2dd4bf",
    "#f472b6",
    "#22d3ee",
    "#a78bfa",
    "#facc15",
    "#fb7185",
    "#94a3b8",
    "#4ade80",
  ],
  pass: "#4cc38a",
  fail: "#e5484d",
  warn: "#f59e0b",
};

export function chartTheme(isDark: boolean): ChartTheme {
  return isDark ? DARK : LIGHT;
}

/** Pick a series color by index, wrapping around the palette. */
export function seriesColor(theme: ChartTheme, index: number): string {
  return theme.series[index % theme.series.length];
}

type AxisLayout = Partial<Layout["xaxis"]>;

/** True for an unset, `transparent` or zero-alpha `rgba()` color. */
function isTransparent(color: unknown): boolean {
  if (color === undefined || color === null) return true;
  const value = String(color).trim().toLowerCase();
  return value === "transparent" || /^rgba\(.*,\s*0(?:\.0+)?\s*\)$/.test(value);
}

function themedAxis(axis: AxisLayout | undefined, t: ChartTheme): AxisLayout {
  const title = axis?.title;
  return {
    gridcolor: t.grid,
    zerolinecolor: t.grid,
    linecolor: t.grid,
    tickfont: { color: t.muted, ...(axis?.tickfont ?? {}) },
    ...axis,
    // A fetched figure may carry `title: null`, and `typeof null === "object"`.
    title:
      title !== null && typeof title === "object"
        ? { ...title, font: { color: t.muted, ...(title.font ?? {}) } }
        : title,
  };
}

/**
 * Fill in the chart chrome a caller did not set: transparent backgrounds, hairline grid, muted
 * ticks and legend, the interface font and the shared colorway. Caller values always win.
 *
 * A figure that paints its own `paper_bgcolor` keeps its own text, grid and series colors: the
 * theme cannot tell which text color reads on that background, so it only supplies the font
 * family.
 */
export function themedLayout(layout: Partial<Layout> | undefined, t: ChartTheme): Partial<Layout> {
  const l = layout ?? {};
  const hoverlabel = { font: { family: sansFontFamily }, ...(l.hoverlabel ?? {}) };
  if (!isTransparent(l.paper_bgcolor)) {
    return { ...l, font: { family: sansFontFamily, ...(l.font ?? {}) }, hoverlabel };
  }
  const axes: Partial<Layout> = {};
  for (const key of Object.keys(l) as (keyof Layout)[]) {
    if (/^[xy]axis\d*$/.test(key)) {
      (axes as Record<string, unknown>)[key] = themedAxis(l[key] as AxisLayout, t);
    }
  }
  return {
    colorway: [...t.series],
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    xaxis: themedAxis(l.xaxis, t),
    yaxis: themedAxis(l.yaxis, t),
    ...l,
    ...axes,
    font: { family: sansFontFamily, color: t.text, ...(l.font ?? {}) },
    legend: {
      bgcolor: "transparent",
      borderwidth: 0,
      font: { color: t.muted },
      ...(l.legend ?? {}),
    },
    hoverlabel,
  };
}
