import type { Theme } from "@earendil-works/pi-coding-agent";
import { truncateToWidth } from "@earendil-works/pi-tui";

import { firstString } from "./payload.js";
import { ansi, boxed, compactDate, formatNumber } from "./render.js";

export type TimeseriesPoint = {
  series: string;
  value: number;
  at?: string;
  unit?: string;
  taskId?: string;
  executionId?: string;
};

export function timeseriesPoints(payload: unknown): TimeseriesPoint[] {
  const points: TimeseriesPoint[] = [];
  const addPoint = (series: string, item: unknown) => {
    if (!item || typeof item !== "object") return;
    const object = item as Record<string, unknown>;
    const value = object.value;
    if (typeof value !== "number" || !Number.isFinite(value)) return;
    points.push({
      series,
      value,
      at: firstString(object, ["calibrated_at", "timestamp", "created_at", "start_at"]),
      unit: firstString(object, ["unit"]),
      taskId: firstString(object, ["task_id"]),
      executionId: firstString(object, ["execution_id"]),
    });
  };
  const visit = (value: unknown, series = "series") => {
    if (Array.isArray(value)) {
      for (const item of value) addPoint(series, item);
      return;
    }
    if (!value || typeof value !== "object") return;
    const object = value as Record<string, unknown>;
    if ("value" in object) {
      addPoint(series, object);
      return;
    }
    for (const [key, nested] of Object.entries(object)) visit(nested, key);
  };
  if (payload && typeof payload === "object" && "data" in payload) visit((payload as Record<string, unknown>).data);
  else visit(payload);
  return points.sort((a, b) => (a.at ?? "").localeCompare(b.at ?? ""));
}

function samplePoints(points: TimeseriesPoint[], width: number): TimeseriesPoint[] {
  if (points.length <= width) return points;
  const sampled: TimeseriesPoint[] = [];
  for (let i = 0; i < width; i++) sampled.push(points[Math.round(i * (points.length - 1) / (width - 1))]);
  return sampled;
}

export function plotSeriesLines(points: TimeseriesPoint[], options: { title: string; height?: number; width?: number; color?: boolean }): string[] {
  const height = Math.max(3, Math.min(20, options.height ?? 8));
  const plotWidth = Math.max(8, Math.min(100, options.width ?? 60));
  const accent = (text: string) => options.color ? ansi("1;36", text) : text;
  const muted = (text: string) => options.color ? ansi("90", text) : text;
  if (points.length === 0) return boxed(options.title, [muted("no numeric data")], options.color);

  const sampled = samplePoints(points, plotWidth);
  const values = sampled.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const grid = Array.from({ length: height }, () => Array.from({ length: sampled.length }, () => " "));
  sampled.forEach((point, col) => {
    const row = height - 1 - Math.round((point.value - min) / span * (height - 1));
    grid[Math.max(0, Math.min(height - 1, row))][col] = "●";
  });
  const yLabelWidth = Math.max(formatNumber(max).length, formatNumber(min).length, 6);
  const rows = grid.map((row, index) => {
    const value = max - (span * index / (height - 1));
    return `${formatNumber(value).padStart(yLabelWidth)} ┤${row.join("")}`;
  });
  const unit = points.find((point) => point.unit)?.unit;
  const first = points[0];
  const last = points[points.length - 1];
  const body = [
    `${muted("series")} ${accent([...new Set(points.map((point) => point.series))].join(", "))}${unit ? `  ${muted("unit")} ${unit}` : ""}`,
    `${muted("count")} ${points.length}  ${muted("min")} ${formatNumber(Math.min(...points.map((point) => point.value)))}  ${muted("max")} ${formatNumber(Math.max(...points.map((point) => point.value)))}  ${muted("last")} ${formatNumber(last.value)}`,
    `${muted("range")} ${compactDate(first.at)} → ${compactDate(last.at)}`,
    "",
    ...rows,
    `${" ".repeat(yLabelWidth)} └${"─".repeat(sampled.length)}`,
  ];
  return boxed(options.title, body, options.color);
}

export function timeseriesPlotComponent(data: unknown, title: string, _theme: Theme) {
  return {
    render(width: number) {
      const points = timeseriesPoints(data);
      return plotSeriesLines(points, { title, width: Math.max(8, width - 16) }).map((line) => truncateToWidth(line, width));
    },
    invalidate() {},
  };
}
