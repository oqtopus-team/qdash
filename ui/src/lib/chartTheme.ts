import type { Layout } from "plotly.js";

import { sansFontFamily } from "@/lib/fonts";

/**
 * One palette for every Plotly chart. The brand primary leads; the other series colors are muted
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

// Light series are muted, mid-lightness hues that each read at 5:1 or more on base-100.
// pass/fail/warn match the light status colors.
const LIGHT: ChartTheme = {
  text: "#3c3c43",
  muted: "rgba(60, 60, 67, 0.6)",
  grid: "rgba(60, 60, 67, 0.1)",
  accent: "#3d5a99",
  secondary: "#a0582b",
  series: [
    "#3d5a99",
    "#a0582b",
    "#20766f",
    "#924b86",
    "#2a6990",
    "#6c5aa8",
    "#6e6a18",
    "#b0475e",
    "#5b6573",
    "#4b7a26",
  ],
  pass: "#2b7350",
  fail: "#ad3838",
  warn: "#8c5c0e",
};

// Dark series are lower-chroma than the light set and alternate lightness so neighbours stay
// apart; each reads at 4.5:1 or more on base-100. pass/fail/warn match the dark status colors.
const DARK: ChartTheme = {
  text: "#e5e5e7",
  muted: "rgba(229, 229, 231, 0.6)",
  grid: "rgba(229, 229, 231, 0.1)",
  accent: "#7f9fdc",
  secondary: "#c98f4a",
  series: [
    "#7f9fdc",
    "#c98f4a",
    "#4fa293",
    "#d39cb9",
    "#7cc0d8",
    "#ae9ee0",
    "#d8c76e",
    "#c9706f",
    "#9aa4b2",
    "#79b77a",
  ],
  pass: "#62b88c",
  fail: "#e07a78",
  warn: "#d6a654",
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
