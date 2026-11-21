import { firstString } from "./payload.js";

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
