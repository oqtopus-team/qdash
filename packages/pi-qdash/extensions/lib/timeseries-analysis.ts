import { readFileSync, statSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";

export type NumericTimeseriesPoint = { at: string | number | Date; value: number };
export type NumericTimeseries = {
  label: string;
  unit?: string;
  source: "qdash" | "csv";
  points: NumericTimeseriesPoint[];
};

export type CsvTimeFormat =
  | "iso"
  | "yyyy/M/d H:mm"
  | "yyyy-MM-dd HH:mm:ss"
  | "unix-seconds"
  | "unix-milliseconds";

export type CsvValueColumn = {
  column: string;
  label?: string;
  unit?: string;
  scale?: number;
  offset?: number;
};

export type ExternalCsvSpec = {
  path: string;
  timeColumn: string;
  valueColumns: CsvValueColumn[];
  timeFormat?: CsvTimeFormat;
  timezoneOffsetMinutes?: number;
  delimiter?: string;
  skipRows?: number;
  filters?: Record<string, string[]>;
};

export type CsvInspection = {
  path: string;
  headers: string[];
  dataRows: number;
  scannedRows: number;
  columns: Array<{
    column: string;
    nonEmpty: number;
    numeric: number;
    numericFraction: number;
    min?: number;
    max?: number;
    samples: string[];
  }>;
  time?: {
    column: string;
    valid: number;
    invalid: number;
    firstAt?: string;
    lastAt?: string;
    medianCadenceMinutes?: number;
  };
};

export type TimeseriesTransformOptions = {
  startAt?: string;
  endAt?: string;
  resampleMinutes?: number;
  smoothingWindowMinutes?: number;
  detrend?: "none" | "linear";
  normalize?: "none" | "zscore";
  maxInterpolationGapMinutes?: number;
  periodSearch?: { minMinutes: number; maxMinutes: number; stepMinutes?: number };
  includeAlignedData?: boolean;
};

export type SeriesStatistics = {
  label: string;
  source: "qdash" | "csv";
  unit?: string;
  inputPoints: number;
  firstAt: string;
  lastAt: string;
  min: number;
  max: number;
  mean: number;
  standardDeviation: number;
};

export type PairwiseComparison = {
  left: string;
  right: string;
  correlation: number | null;
  phaseDifferenceDegrees?: number;
};

export type PeriodicFit = {
  label: string;
  periodMinutes: number;
  phaseDegrees: number;
  periodicExplainedFraction: number;
};

export type TimeseriesComparison = {
  overlap: {
    startAt: string;
    endAt: string;
    durationMinutes: number;
    alignedPoints: number;
    resampleMinutes: number;
    observedCycles?: number;
  };
  transforms: {
    smoothingWindowMinutes: number;
    detrend: "none" | "linear";
    normalize: "none" | "zscore";
    maxInterpolationGapMinutes: number;
  };
  series: SeriesStatistics[];
  pairs: PairwiseComparison[];
  periodicFits?: PeriodicFit[];
  warnings: string[];
  alignedData?: Array<{ at: string; values: Record<string, number> }>;
};

const MAX_CSV_BYTES = 10 * 1024 * 1024;
const MAX_GRID_POINTS = 100_000;

function parseCsv(text: string, delimiter: string): string[][] {
  if (delimiter.length !== 1) throw new Error("CSV delimiter must be exactly one character");
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index++;
      } else if (character === '"') quoted = false;
      else field += character;
      continue;
    }
    if (character === '"') quoted = true;
    else if (character === delimiter) {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else field += character;
  }
  if (quoted) throw new Error("CSV contains an unterminated quoted field");
  if (field.length > 0 || row.length > 0) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows;
}

function timestampFromParts(parts: number[], timezoneOffsetMinutes: number): number {
  const [year, month, day, hour = 0, minute = 0, second = 0] = parts;
  return Date.UTC(year, month - 1, day, hour, minute, second) - timezoneOffsetMinutes * 60_000;
}

function parseCsvTimestamp(value: string, format: CsvTimeFormat, timezoneOffsetMinutes?: number): number {
  const trimmed = value.trim();
  if (format === "unix-seconds" || format === "unix-milliseconds") {
    const numeric = Number(trimmed);
    if (!Number.isFinite(numeric)) throw new Error(`Invalid ${format} timestamp: ${value}`);
    return format === "unix-seconds" ? numeric * 1000 : numeric;
  }
  if (format === "iso") {
    const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed);
    if (!hasZone && timezoneOffsetMinutes === undefined) {
      throw new Error("Naive ISO timestamps require timezoneOffsetMinutes");
    }
    const zoned = hasZone
      ? trimmed
      : `${trimmed}${formatOffset(timezoneOffsetMinutes ?? 0)}`;
    const parsed = Date.parse(zoned);
    if (!Number.isFinite(parsed)) throw new Error(`Invalid ISO timestamp: ${value}`);
    return parsed;
  }
  if (timezoneOffsetMinutes === undefined) {
    throw new Error(`${format} timestamps require timezoneOffsetMinutes`);
  }
  const expression = format === "yyyy/M/d H:mm"
    ? /^(\d{4})\/(\d{1,2})\/(\d{1,2})\s+(\d{1,2}):(\d{2})$/
    : /^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})$/;
  const match = trimmed.match(expression);
  if (!match) throw new Error(`Timestamp does not match ${format}: ${value}`);
  return timestampFromParts(match.slice(1).map(Number), timezoneOffsetMinutes);
}

function formatOffset(minutes: number): string {
  const sign = minutes >= 0 ? "+" : "-";
  const absolute = Math.abs(minutes);
  return `${sign}${String(Math.floor(absolute / 60)).padStart(2, "0")}:${String(absolute % 60).padStart(2, "0")}`;
}

function csvRows(pathInput: string, cwd: string, delimiter = ",", skipRows = 0): { path: string; rows: string[][]; headers: string[] } {
  const rawPath = pathInput.startsWith("@") ? pathInput.slice(1) : pathInput;
  const path = isAbsolute(rawPath) ? rawPath : resolve(cwd, rawPath);
  const size = statSync(path).size;
  if (size > MAX_CSV_BYTES) throw new Error(`CSV exceeds 10 MB limit: ${path}`);
  if (!Number.isInteger(skipRows) || skipRows < 0) throw new Error("skipRows must be a non-negative integer");
  const rows = parseCsv(readFileSync(path, "utf8"), delimiter).slice(skipRows);
  if (rows.length < 2) throw new Error(`CSV has no data rows: ${path}`);
  return { path, rows, headers: rows[0].map((header) => header.trim().replace(/^\uFEFF/, "")) };
}

function findHeader(headers: string[], requested: string): number {
  const exact = headers.indexOf(requested);
  if (exact >= 0) return exact;
  const normalized = requested.trim().replace(/^#/, "");
  return headers.findIndex((header) => header.replace(/^#/, "") === normalized);
}

export function inspectExternalCsv(spec: {
  path: string;
  delimiter?: string;
  skipRows?: number;
  timeColumn?: string;
  timeFormat?: CsvTimeFormat;
  timezoneOffsetMinutes?: number;
  scanRows?: number;
}, cwd: string): CsvInspection {
  const { path, rows, headers } = csvRows(spec.path, cwd, spec.delimiter, spec.skipRows);
  const scanLimit = spec.scanRows ?? 10_000;
  if (!Number.isInteger(scanLimit) || scanLimit < 1 || scanLimit > 100_000) throw new Error("scanRows must be an integer from 1 to 100000");
  const data = rows.slice(1, scanLimit + 1).filter((row) => !row.every((field) => field.trim() === ""));
  const columns = headers.map((column, index) => {
    const values = data.map((row) => (row[index] ?? "").trim()).filter(Boolean);
    const numericValues = values.map(Number).filter(Number.isFinite);
    return {
      column,
      nonEmpty: values.length,
      numeric: numericValues.length,
      numericFraction: values.length === 0 ? 0 : numericValues.length / values.length,
      min: numericValues.length === 0 ? undefined : Math.min(...numericValues),
      max: numericValues.length === 0 ? undefined : Math.max(...numericValues),
      samples: [...new Set(values)].slice(0, 3),
    };
  });
  const inspection: CsvInspection = { path, headers, dataRows: rows.length - 1, scannedRows: data.length, columns };
  if (spec.timeColumn) {
    const index = findHeader(headers, spec.timeColumn);
    if (index < 0) throw new Error(`CSV time column not found: ${spec.timeColumn}`);
    const format = spec.timeFormat ?? "iso";
    const timestamps: number[] = [];
    let invalid = 0;
    for (const row of data) {
      try {
        timestamps.push(parseCsvTimestamp(row[index] ?? "", format, spec.timezoneOffsetMinutes));
      } catch {
        invalid++;
      }
    }
    timestamps.sort((a, b) => a - b);
    const intervals = timestamps.slice(1).map((value, item) => (value - timestamps[item]) / 60_000).filter((value) => value > 0).sort((a, b) => a - b);
    inspection.time = {
      column: headers[index],
      valid: timestamps.length,
      invalid,
      firstAt: timestamps.length ? new Date(timestamps[0]).toISOString() : undefined,
      lastAt: timestamps.length ? new Date(timestamps.at(-1)!).toISOString() : undefined,
      medianCadenceMinutes: intervals.length ? intervals[Math.floor(intervals.length / 2)] : undefined,
    };
  }
  return inspection;
}

export function csvInspectionText(inspection: CsvInspection): string {
  const lines = [
    `CSV ${inspection.path}`,
    `rows ${inspection.dataRows} (scanned ${inspection.scannedRows})`,
    `headers ${inspection.headers.join(", ")}`,
    "",
    "Columns",
    ...inspection.columns.map((column) => `- ${column.column}: non-empty=${column.nonEmpty}, numeric=${column.numeric} (${(column.numericFraction * 100).toFixed(1)}%)${column.min === undefined ? "" : `, range=${column.min}..${column.max}`}, samples=${column.samples.map((sample) => JSON.stringify(sample)).join(", ")}`),
  ];
  if (inspection.time) lines.push("", `Time ${inspection.time.column}: valid=${inspection.time.valid}, invalid=${inspection.time.invalid}, range=${inspection.time.firstAt ?? "n/a"}..${inspection.time.lastAt ?? "n/a"}, median cadence=${inspection.time.medianCadenceMinutes ?? "n/a"} min`);
  return lines.join("\n");
}

export function loadExternalCsvSeries(spec: ExternalCsvSpec, cwd: string): NumericTimeseries[] {
  const { rows, headers } = csvRows(spec.path, cwd, spec.delimiter, spec.skipRows);
  const timeFormat = spec.timeFormat ?? "iso";
  const supportedFormats: CsvTimeFormat[] = ["iso", "yyyy/M/d H:mm", "yyyy-MM-dd HH:mm:ss", "unix-seconds", "unix-milliseconds"];
  if (!supportedFormats.includes(timeFormat)) throw new Error(`Unsupported CSV timeFormat: ${String(timeFormat)}`);
  const findHeaderIndex = (requested: string) => findHeader(headers, requested);
  const timeIndex = findHeaderIndex(spec.timeColumn);
  if (timeIndex < 0) throw new Error(`CSV time column not found: ${spec.timeColumn}`);
  const columns = spec.valueColumns.map((column) => {
    const index = findHeaderIndex(column.column);
    if (index < 0) throw new Error(`CSV value column not found: ${column.column}`);
    return { ...column, index };
  });
  const filters = Object.entries(spec.filters ?? {}).map(([column, accepted]) => {
    const index = findHeaderIndex(column);
    if (index < 0) throw new Error(`CSV filter column not found: ${column}`);
    if (accepted.length === 0) throw new Error(`CSV filter ${column} must contain at least one accepted value`);
    return { index, accepted: new Set(accepted) };
  });
  const output = columns.map((column) => ({
    label: column.label ?? column.column,
    unit: column.unit,
    source: "csv" as const,
    points: [] as NumericTimeseriesPoint[],
  }));
  for (let rowIndex = 1; rowIndex < rows.length; rowIndex++) {
    const row = rows[rowIndex];
    if (row.every((field) => field.trim() === "")) continue;
    if (filters.some((filter) => !filter.accepted.has((row[filter.index] ?? "").trim()))) continue;
    let at: number;
    try {
      at = parseCsvTimestamp(row[timeIndex] ?? "", timeFormat, spec.timezoneOffsetMinutes);
    } catch (error) {
      throw new Error(`CSV row ${rowIndex + 1}: ${error instanceof Error ? error.message : String(error)}`);
    }
    columns.forEach((column, columnIndex) => {
      const value = Number((row[column.index] ?? "").trim());
      if (!Number.isFinite(value)) return;
      output[columnIndex].points.push({
        at,
        value: value * (column.scale ?? 1) + (column.offset ?? 0),
      });
    });
  }
  return output;
}

function epoch(value: string | number | Date): number {
  const parsed = typeof value === "number" ? value : value instanceof Date ? value.getTime() : Date.parse(value);
  if (!Number.isFinite(parsed)) throw new Error(`Invalid timeseries timestamp: ${String(value)}`);
  return parsed;
}

function preparedPoints(series: NumericTimeseries, start?: number, end?: number): Array<{ at: number; value: number }> {
  const byTime = new Map<number, number>();
  for (const point of series.points) {
    if (!Number.isFinite(point.value)) continue;
    const at = epoch(point.at);
    if ((start !== undefined && at < start) || (end !== undefined && at > end)) continue;
    byTime.set(at, point.value);
  }
  return [...byTime.entries()].map(([at, value]) => ({ at, value })).sort((a, b) => a.at - b.at);
}

function interpolate(points: Array<{ at: number; value: number }>, at: number, maxGapMs: number): number | undefined {
  let low = 0;
  let high = points.length - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (points[middle].at < at) low = middle + 1;
    else if (points[middle].at > at) high = middle - 1;
    else return points[middle].value;
  }
  const right = points[low];
  const left = points[low - 1];
  if (!left || !right || right.at - left.at > maxGapMs) return undefined;
  return left.value + (right.value - left.value) * ((at - left.at) / (right.at - left.at));
}

function centeredMean(values: number[], width: number): number[] {
  if (width <= 1) return [...values];
  const before = Math.floor(width / 2);
  const after = width - before - 1;
  return values.map((_value, index) => {
    const slice = values.slice(Math.max(0, index - before), Math.min(values.length, index + after + 1));
    return slice.reduce((sum, value) => sum + value, 0) / slice.length;
  });
}

function linearDetrend(values: number[]): number[] {
  const count = values.length;
  const meanX = (count - 1) / 2;
  const meanY = values.reduce((sum, value) => sum + value, 0) / count;
  let numerator = 0;
  let denominator = 0;
  values.forEach((value, index) => {
    numerator += (index - meanX) * (value - meanY);
    denominator += (index - meanX) ** 2;
  });
  const slope = denominator === 0 ? 0 : numerator / denominator;
  return values.map((value, index) => value - (meanY + slope * (index - meanX)));
}

function zscore(values: number[]): number[] {
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(1, values.length - 1);
  const deviation = Math.sqrt(variance);
  return deviation === 0 ? values.map(() => 0) : values.map((value) => (value - mean) / deviation);
}

function pearson(left: number[], right: number[]): number | null {
  if (left.length < 3 || right.length !== left.length) return null;
  const leftMean = left.reduce((sum, value) => sum + value, 0) / left.length;
  const rightMean = right.reduce((sum, value) => sum + value, 0) / right.length;
  let numerator = 0;
  let leftSquare = 0;
  let rightSquare = 0;
  left.forEach((value, index) => {
    const a = value - leftMean;
    const b = right[index] - rightMean;
    numerator += a * b;
    leftSquare += a * a;
    rightSquare += b * b;
  });
  const denominator = Math.sqrt(leftSquare * rightSquare);
  return denominator === 0 ? null : numerator / denominator;
}

function solve(matrix: number[][], vector: number[]): number[] | undefined {
  const augmented = matrix.map((row, index) => [...row, vector[index]]);
  for (let column = 0; column < matrix.length; column++) {
    let pivot = column;
    for (let row = column + 1; row < matrix.length; row++) {
      if (Math.abs(augmented[row][column]) > Math.abs(augmented[pivot][column])) pivot = row;
    }
    if (Math.abs(augmented[pivot][column]) < 1e-12) return undefined;
    [augmented[column], augmented[pivot]] = [augmented[pivot], augmented[column]];
    const divisor = augmented[column][column];
    for (let index = column; index <= matrix.length; index++) augmented[column][index] /= divisor;
    for (let row = 0; row < matrix.length; row++) {
      if (row === column) continue;
      const factor = augmented[row][column];
      for (let index = column; index <= matrix.length; index++) augmented[row][index] -= factor * augmented[column][index];
    }
  }
  return augmented.map((row) => row[matrix.length]);
}

function sinusoidFit(values: number[], periodSamples: number): { explained: number; phase: number } | undefined {
  const rows = values.map((_value, index) => [1, index, Math.sin(2 * Math.PI * index / periodSamples), Math.cos(2 * Math.PI * index / periodSamples)]);
  const normal = Array.from({ length: 4 }, (_unused, row) => Array.from({ length: 4 }, (_unused2, column) => rows.reduce((sum, item) => sum + item[row] * item[column], 0)));
  const target = Array.from({ length: 4 }, (_unused, column) => rows.reduce((sum, item, index) => sum + item[column] * values[index], 0));
  const coefficients = solve(normal, target);
  if (!coefficients) return undefined;
  const baseline = linearDetrend(values);
  const residual = values.map((value, index) => value - rows[index].reduce((sum, item, column) => sum + item * coefficients[column], 0));
  const baselineSquares = baseline.reduce((sum, value) => sum + value ** 2, 0);
  const residualSquares = residual.reduce((sum, value) => sum + value ** 2, 0);
  return {
    explained: baselineSquares === 0 ? 0 : Math.max(0, Math.min(1, 1 - residualSquares / baselineSquares)),
    phase: Math.atan2(coefficients[3], coefficients[2]),
  };
}

function descriptive(series: NumericTimeseries, points: Array<{ at: number; value: number }>): SeriesStatistics {
  const values = points.map((point) => point.value);
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  return {
    label: series.label,
    source: series.source,
    unit: series.unit,
    inputPoints: values.length,
    firstAt: new Date(points[0].at).toISOString(),
    lastAt: new Date(points.at(-1)!.at).toISOString(),
    min: Math.min(...values),
    max: Math.max(...values),
    mean,
    standardDeviation: Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(1, values.length - 1)),
  };
}

export function compareTimeseries(inputSeries: NumericTimeseries[], options: TimeseriesTransformOptions = {}): TimeseriesComparison {
  if (inputSeries.length < 2) throw new Error("At least two timeseries are required");
  const labels = inputSeries.map((series) => series.label);
  if (new Set(labels).size !== labels.length) throw new Error("Timeseries labels must be unique");
  const requestedStart = options.startAt ? epoch(options.startAt) : undefined;
  const requestedEnd = options.endAt ? epoch(options.endAt) : undefined;
  const prepared = inputSeries.map((series) => preparedPoints(series, requestedStart, requestedEnd));
  prepared.forEach((points, index) => {
    if (points.length < 2) throw new Error(`Timeseries ${inputSeries[index].label} has fewer than two usable points`);
  });
  const start = Math.max(...prepared.map((points) => points[0].at));
  const end = Math.min(...prepared.map((points) => points.at(-1)!.at));
  if (start >= end) throw new Error("Timeseries have no overlapping time range");
  const stepMinutes = options.resampleMinutes ?? 1;
  if (!(stepMinutes > 0)) throw new Error("resampleMinutes must be greater than zero");
  const stepMs = stepMinutes * 60_000;
  const sourceCadences = prepared.map((points) => {
    const intervals = points.slice(1).map((point, index) => (point.at - points[index].at) / 60_000).filter((value) => value > 0).sort((a, b) => a - b);
    return intervals.length === 0 ? stepMinutes : intervals[Math.floor(intervals.length / 2)];
  });
  const maxGapMinutes = options.maxInterpolationGapMinutes ?? Math.max(stepMinutes * 5, ...sourceCadences.map((cadence) => cadence * 3));
  if (!(maxGapMinutes > 0)) throw new Error("maxInterpolationGapMinutes must be greater than zero");
  const gridCount = Math.floor((end - start) / stepMs) + 1;
  if (gridCount > MAX_GRID_POINTS) throw new Error(`Aligned grid exceeds ${MAX_GRID_POINTS} points; increase resampleMinutes or shorten the range`);
  const alignedAt: number[] = [];
  const rawAligned = inputSeries.map(() => [] as number[]);
  for (let at = start; at <= end; at += stepMs) {
    const values = prepared.map((points) => interpolate(points, at, maxGapMinutes * 60_000));
    if (values.some((value) => value === undefined)) continue;
    alignedAt.push(at);
    values.forEach((value, index) => rawAligned[index].push(value!));
  }
  if (alignedAt.length < 3) throw new Error("Fewer than three aligned points remain after interpolation gap filtering");
  const smoothingMinutes = options.smoothingWindowMinutes ?? 0;
  if (smoothingMinutes < 0) throw new Error("smoothingWindowMinutes must not be negative");
  const smoothingWidth = Math.max(1, Math.round(smoothingMinutes / stepMinutes));
  const transformed = rawAligned.map((values) => {
    let output = centeredMean(values, smoothingWidth);
    if ((options.detrend ?? "none") === "linear") output = linearDetrend(output);
    if ((options.normalize ?? "none") === "zscore") output = zscore(output);
    return output;
  });
  const pairs: PairwiseComparison[] = [];
  for (let left = 0; left < inputSeries.length; left++) {
    for (let right = left + 1; right < inputSeries.length; right++) {
      pairs.push({ left: labels[left], right: labels[right], correlation: pearson(transformed[left], transformed[right]) });
    }
  }
  let periodicFits: PeriodicFit[] | undefined;
  let observedCycles: number | undefined;
  const warnings: string[] = [];
  if (options.periodSearch) {
    const { minMinutes, maxMinutes, stepMinutes: searchStep = Math.max(0.1, stepMinutes / 10) } = options.periodSearch;
    if (!(minMinutes > 0 && maxMinutes > minMinutes && searchStep > 0)) throw new Error("periodSearch must have 0 < minMinutes < maxMinutes and a positive stepMinutes");
    let bestPeriod = minMinutes;
    let bestScore = Number.NEGATIVE_INFINITY;
    for (let period = minMinutes; period <= maxMinutes + searchStep / 2; period += searchStep) {
      const fits = transformed.map((values) => sinusoidFit(values, period / stepMinutes));
      const score = fits.reduce((sum, fit) => sum + (fit?.explained ?? 0), 0);
      if (score > bestScore) {
        bestScore = score;
        bestPeriod = period;
      }
    }
    periodicFits = transformed.map((values, index) => {
      const fit = sinusoidFit(values, bestPeriod / stepMinutes)!;
      return {
        label: labels[index],
        periodMinutes: bestPeriod,
        phaseDegrees: ((fit.phase * 180 / Math.PI) % 360 + 360) % 360,
        periodicExplainedFraction: fit.explained,
      };
    });
    for (const pair of pairs) {
      const left = periodicFits.find((fit) => fit.label === pair.left)!;
      const right = periodicFits.find((fit) => fit.label === pair.right)!;
      let difference = left.phaseDegrees - right.phaseDegrees;
      while (difference > 180) difference -= 360;
      while (difference <= -180) difference += 360;
      pair.phaseDifferenceDegrees = difference;
    }
    observedCycles = ((alignedAt.at(-1)! - alignedAt[0]) / 60_000) / bestPeriod;
    if (observedCycles < 5) warnings.push(`Only ${observedCycles.toFixed(1)} cycles of the selected period are observed; periodic inference is preliminary.`);
  }
  warnings.push("Correlation and shared periodicity do not by themselves establish a causal direction or exclude a common driver.");
  if (smoothingMinutes > 0) warnings.push("Smoothing and interpolation introduce autocorrelation; aligned points are not independent observations.");
  const result: TimeseriesComparison = {
    overlap: {
      startAt: new Date(alignedAt[0]).toISOString(),
      endAt: new Date(alignedAt.at(-1)!).toISOString(),
      durationMinutes: (alignedAt.at(-1)! - alignedAt[0]) / 60_000,
      alignedPoints: alignedAt.length,
      resampleMinutes: stepMinutes,
      observedCycles,
    },
    transforms: {
      smoothingWindowMinutes: smoothingMinutes,
      detrend: options.detrend ?? "none",
      normalize: options.normalize ?? "none",
      maxInterpolationGapMinutes: maxGapMinutes,
    },
    series: inputSeries.map((series, index) => descriptive(series, prepared[index])),
    pairs,
    periodicFits,
    warnings,
  };
  if (options.includeAlignedData) {
    if (alignedAt.length > 5_000) throw new Error("includeAlignedData is limited to 5,000 aligned rows; shorten the range or increase resampleMinutes");
    result.alignedData = alignedAt.map((at, row) => ({
      at: new Date(at).toISOString(),
      values: Object.fromEntries(labels.map((label, column) => [label, transformed[column][row]])),
    }));
  }
  return result;
}

function number(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined || !Number.isFinite(value) ? "n/a" : value.toFixed(digits);
}

export function timeseriesComparisonText(comparison: TimeseriesComparison): string {
  const lines = [
    "Timeseries comparison",
    `overlap ${comparison.overlap.startAt} → ${comparison.overlap.endAt}`,
    `aligned ${comparison.overlap.alignedPoints} points every ${comparison.overlap.resampleMinutes} min`,
    `transform smooth=${comparison.transforms.smoothingWindowMinutes} min detrend=${comparison.transforms.detrend} normalize=${comparison.transforms.normalize}`,
    "",
    "Series",
    ...comparison.series.map((series) => `- ${series.label} (${series.source}): n=${series.inputPoints}, min=${number(series.min)}${series.unit ? ` ${series.unit}` : ""}, max=${number(series.max)}${series.unit ? ` ${series.unit}` : ""}`),
    "",
    "Pairwise correlation",
    ...comparison.pairs.map((pair) => `- ${pair.left} vs ${pair.right}: r=${number(pair.correlation)}${pair.phaseDifferenceDegrees === undefined ? "" : `, phase=${number(pair.phaseDifferenceDegrees, 1)}°`}`),
  ];
  if (comparison.periodicFits) {
    lines.push("", "Shared-period fit");
    for (const fit of comparison.periodicFits) {
      lines.push(`- ${fit.label}: period=${number(fit.periodMinutes, 1)} min, phase=${number(fit.phaseDegrees, 1)}°, explained=${number(fit.periodicExplainedFraction * 100, 1)}%`);
    }
  }
  lines.push("", "Warnings", ...comparison.warnings.map((warning) => `- ${warning}`));
  return lines.join("\n");
}
