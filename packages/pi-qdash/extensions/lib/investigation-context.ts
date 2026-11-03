import type { CsvTimeFormat, ExternalCsvSpec, TimeseriesTransformOptions } from "./timeseries-analysis.js";

export type InvestigationQDashSeries = {
  parameter: string;
  qid?: string;
  tag?: string;
  label?: string;
  unit?: string;
  scale?: number;
  offset?: number;
};

export type TimeseriesInvestigationContext = {
  name?: string;
  startAt?: string;
  endAt?: string;
  timezoneOffsetMinutes?: number;
  tag?: string;
  qdashSeries?: InvestigationQDashSeries[];
  csvSeries?: ExternalCsvSpec[];
  analysis?: Omit<TimeseriesTransformOptions, "startAt" | "endAt" | "includeAlignedData">;
};

const TIME_FORMATS: CsvTimeFormat[] = ["iso", "yyyy/M/d H:mm", "yyyy-MM-dd HH:mm:ss", "unix-seconds", "unix-milliseconds"];

function optionalString(value: unknown, path: string): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string" || !value.trim()) throw new Error(`${path} must be a non-empty string`);
  return value.trim();
}

function requiredString(value: unknown, path: string): string {
  const result = optionalString(value, path);
  if (result === undefined) throw new Error(`${path} is required`);
  return result;
}

function optionalNumber(value: unknown, path: string): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${path} must be a finite number`);
  return value;
}

function validateIso(value: string | undefined, path: string): void {
  if (value !== undefined && !Number.isFinite(Date.parse(value))) throw new Error(`${path} must be a valid ISO timestamp`);
}

function validateQDashSeries(value: unknown): InvestigationQDashSeries[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || value.length > 12) throw new Error("investigation.qdashSeries must be an array with at most 12 entries");
  return value.map((item, index) => {
    if (!item || typeof item !== "object") throw new Error(`investigation.qdashSeries[${index}] must be an object`);
    const input = item as Record<string, unknown>;
    return {
      parameter: requiredString(input.parameter, `investigation.qdashSeries[${index}].parameter`),
      qid: optionalString(input.qid, `investigation.qdashSeries[${index}].qid`),
      tag: optionalString(input.tag, `investigation.qdashSeries[${index}].tag`),
      label: optionalString(input.label, `investigation.qdashSeries[${index}].label`),
      unit: optionalString(input.unit, `investigation.qdashSeries[${index}].unit`),
      scale: optionalNumber(input.scale, `investigation.qdashSeries[${index}].scale`),
      offset: optionalNumber(input.offset, `investigation.qdashSeries[${index}].offset`),
    };
  });
}

function validateCsvSeries(value: unknown): ExternalCsvSpec[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || value.length > 8) throw new Error("investigation.csvSeries must be an array with at most 8 entries");
  return value.map((item, index) => {
    if (!item || typeof item !== "object") throw new Error(`investigation.csvSeries[${index}] must be an object`);
    const input = item as Record<string, unknown>;
    if (!Array.isArray(input.valueColumns) || input.valueColumns.length < 1 || input.valueColumns.length > 12) {
      throw new Error(`investigation.csvSeries[${index}].valueColumns must contain 1 to 12 entries`);
    }
    const timeFormat = optionalString(input.timeFormat, `investigation.csvSeries[${index}].timeFormat`) as CsvTimeFormat | undefined;
    if (timeFormat && !TIME_FORMATS.includes(timeFormat)) throw new Error(`Unsupported investigation.csvSeries[${index}].timeFormat: ${timeFormat}`);
    const filters = input.filters === undefined ? undefined : input.filters;
    if (filters !== undefined && (!filters || typeof filters !== "object" || Array.isArray(filters))) {
      throw new Error(`investigation.csvSeries[${index}].filters must be an object of string arrays`);
    }
    const validatedFilters = filters === undefined ? undefined : Object.fromEntries(Object.entries(filters as Record<string, unknown>).map(([column, accepted]) => {
      if (!Array.isArray(accepted) || !accepted.every((entry) => typeof entry === "string")) throw new Error(`investigation.csvSeries[${index}].filters.${column} must be a string array`);
      return [column, accepted];
    }));
    return {
      path: requiredString(input.path, `investigation.csvSeries[${index}].path`),
      timeColumn: requiredString(input.timeColumn, `investigation.csvSeries[${index}].timeColumn`),
      timeFormat,
      timezoneOffsetMinutes: optionalNumber(input.timezoneOffsetMinutes, `investigation.csvSeries[${index}].timezoneOffsetMinutes`),
      delimiter: optionalString(input.delimiter, `investigation.csvSeries[${index}].delimiter`),
      skipRows: optionalNumber(input.skipRows, `investigation.csvSeries[${index}].skipRows`),
      filters: validatedFilters,
      valueColumns: input.valueColumns.map((entry, columnIndex) => {
        if (!entry || typeof entry !== "object") throw new Error(`investigation.csvSeries[${index}].valueColumns[${columnIndex}] must be an object`);
        const column = entry as Record<string, unknown>;
        return {
          column: requiredString(column.column, `investigation.csvSeries[${index}].valueColumns[${columnIndex}].column`),
          label: optionalString(column.label, `investigation.csvSeries[${index}].valueColumns[${columnIndex}].label`),
          unit: optionalString(column.unit, `investigation.csvSeries[${index}].valueColumns[${columnIndex}].unit`),
          scale: optionalNumber(column.scale, `investigation.csvSeries[${index}].valueColumns[${columnIndex}].scale`),
          offset: optionalNumber(column.offset, `investigation.csvSeries[${index}].valueColumns[${columnIndex}].offset`),
        };
      }),
    };
  });
}

function validateAnalysis(value: unknown): TimeseriesInvestigationContext["analysis"] {
  if (value === undefined) return undefined;
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("investigation.analysis must be an object");
  const input = value as Record<string, unknown>;
  const detrend = optionalString(input.detrend, "investigation.analysis.detrend");
  const normalize = optionalString(input.normalize, "investigation.analysis.normalize");
  if (detrend && detrend !== "none" && detrend !== "linear") throw new Error("investigation.analysis.detrend must be none or linear");
  if (normalize && normalize !== "none" && normalize !== "zscore") throw new Error("investigation.analysis.normalize must be none or zscore");
  let periodSearch: { minMinutes: number; maxMinutes: number; stepMinutes?: number } | undefined;
  if (input.periodSearch !== undefined) {
    if (!input.periodSearch || typeof input.periodSearch !== "object" || Array.isArray(input.periodSearch)) throw new Error("investigation.analysis.periodSearch must be an object");
    const period = input.periodSearch as Record<string, unknown>;
    const minMinutes = optionalNumber(period.minMinutes, "investigation.analysis.periodSearch.minMinutes");
    const maxMinutes = optionalNumber(period.maxMinutes, "investigation.analysis.periodSearch.maxMinutes");
    if (minMinutes === undefined || maxMinutes === undefined || minMinutes <= 0 || maxMinutes <= minMinutes) throw new Error("investigation.analysis.periodSearch requires 0 < minMinutes < maxMinutes");
    periodSearch = { minMinutes, maxMinutes, stepMinutes: optionalNumber(period.stepMinutes, "investigation.analysis.periodSearch.stepMinutes") };
  }
  const analysis: TimeseriesInvestigationContext["analysis"] = {
    resampleMinutes: optionalNumber(input.resampleMinutes, "investigation.analysis.resampleMinutes"),
    smoothingWindowMinutes: optionalNumber(input.smoothingWindowMinutes, "investigation.analysis.smoothingWindowMinutes"),
    detrend: detrend as "none" | "linear" | undefined,
    normalize: normalize as "none" | "zscore" | undefined,
    maxInterpolationGapMinutes: optionalNumber(input.maxInterpolationGapMinutes, "investigation.analysis.maxInterpolationGapMinutes"),
    periodSearch,
  };
  if (analysis.resampleMinutes !== undefined && analysis.resampleMinutes <= 0) throw new Error("investigation.analysis.resampleMinutes must be greater than zero");
  if (analysis.smoothingWindowMinutes !== undefined && analysis.smoothingWindowMinutes < 0) throw new Error("investigation.analysis.smoothingWindowMinutes must not be negative");
  if (analysis.maxInterpolationGapMinutes !== undefined && analysis.maxInterpolationGapMinutes <= 0) throw new Error("investigation.analysis.maxInterpolationGapMinutes must be greater than zero");
  if (analysis.periodSearch?.stepMinutes !== undefined && analysis.periodSearch.stepMinutes <= 0) throw new Error("investigation.analysis.periodSearch.stepMinutes must be greater than zero");
  return analysis;
}

export function validateInvestigationContext(value: unknown): TimeseriesInvestigationContext {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("investigation context must be a JSON object");
  const input = value as Record<string, unknown>;
  const context: TimeseriesInvestigationContext = {
    name: optionalString(input.name, "investigation.name"),
    startAt: optionalString(input.startAt, "investigation.startAt"),
    endAt: optionalString(input.endAt, "investigation.endAt"),
    timezoneOffsetMinutes: optionalNumber(input.timezoneOffsetMinutes, "investigation.timezoneOffsetMinutes"),
    tag: optionalString(input.tag, "investigation.tag"),
    qdashSeries: validateQDashSeries(input.qdashSeries),
    csvSeries: validateCsvSeries(input.csvSeries),
    analysis: validateAnalysis(input.analysis),
  };
  validateIso(context.startAt, "investigation.startAt");
  validateIso(context.endAt, "investigation.endAt");
  if (context.startAt && context.endAt && Date.parse(context.startAt) >= Date.parse(context.endAt)) throw new Error("investigation.startAt must be before endAt");
  if (context.timezoneOffsetMinutes !== undefined && (!Number.isInteger(context.timezoneOffsetMinutes) || Math.abs(context.timezoneOffsetMinutes) > 14 * 60)) {
    throw new Error("investigation.timezoneOffsetMinutes must be an integer from -840 to 840");
  }
  if ((context.qdashSeries?.length ?? 0) + (context.csvSeries?.flatMap((series) => series.valueColumns).length ?? 0) < 2) {
    throw new Error("investigation context must define at least two QDash/CSV value series");
  }
  return context;
}

export function investigationContextSummary(context: TimeseriesInvestigationContext): string {
  const qdashCount = context.qdashSeries?.length ?? 0;
  const csvCount = context.csvSeries?.reduce((sum, series) => sum + series.valueColumns.length, 0) ?? 0;
  return `${context.name ?? "unnamed"}: ${qdashCount + csvCount} series, ${context.startAt ?? "auto-start"} → ${context.endAt ?? "auto-end"}${context.tag ? `, tag ${context.tag}` : ""}`;
}
