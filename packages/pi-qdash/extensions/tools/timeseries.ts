import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashClient } from "@oqtopus-team/qdash-client";
import { Type } from "typebox";

import {
  compareTimeseries,
  csvInspectionText,
  inspectExternalCsv,
  loadExternalCsvSeries,
  timeseriesComparisonText,
  type CsvTimeFormat,
  type ExternalCsvSpec,
  type NumericTimeseries,
} from "../lib/timeseries-analysis.js";
import type { TimeseriesInvestigationContext } from "../lib/investigation-context.js";
import { toTextToolResult } from "../lib/results.js";
import { timeseriesPoints } from "../lib/timeseries-plot.js";

type ComparisonToolParams = {
  profile?: string;
  configPath?: string;
  useEnv?: boolean;
  chipId?: string;
  startAt?: string;
  endAt?: string;
  withinHours?: number;
  qdashSeries?: Array<{ parameter: string; qid?: string; tag?: string; label?: string; unit?: string; scale?: number; offset?: number }>;
  csvSeries?: Array<ExternalCsvSpec & { timeFormat?: CsvTimeFormat }>;
  resampleMinutes?: number;
  smoothingWindowMinutes?: number;
  detrend?: string;
  normalize?: string;
  maxInterpolationGapMinutes?: number;
  periodSearch?: { minMinutes: number; maxMinutes: number; stepMinutes?: number };
  includeAlignedData?: boolean;
  useInvestigationContext?: boolean;
};

export type TimeseriesToolDependencies = {
  makeClient: (params: { profile?: string; configPath?: string; useEnv?: boolean }) => Promise<QDashClient>;
  defaultChipId: (client: QDashClient, chipId?: string) => Promise<string>;
  investigationContext?: () => TimeseriesInvestigationContext | undefined;
};

export function registerTimeseriesComparisonTool(pi: ExtensionAPI, dependencies: TimeseriesToolDependencies): void {
  pi.registerTool({
    name: "qdash_inspect_timeseries_csv",
    label: "QDash Inspect Timeseries CSV",
    description: "Inspect a local CSV schema and numeric/time characteristics before mapping it into a QDash timeseries comparison. Read-only; never uploads the file.",
    promptSnippet: "Inspect local CSV columns, numeric ranges, timestamps, and cadence before comparison",
    promptGuidelines: [
      "Use qdash_inspect_timeseries_csv before qdash_compare_timeseries when a local CSV schema, timestamp format, timezone, or numeric columns are not already known.",
      "Do not infer the timezone of naive timestamps from qdash_inspect_timeseries_csv samples; ask for or supply an explicit timezone offset.",
    ],
    parameters: Type.Object({
      path: Type.String({ description: "Local CSV path, absolute or relative to the current working directory." }),
      delimiter: Type.Optional(Type.String({ description: "Single-character delimiter. Defaults to comma." })),
      skipRows: Type.Optional(Type.Number({ description: "Rows before the header. Defaults to 0." })),
      timeColumn: Type.Optional(Type.String({ description: "Optional timestamp column to validate." })),
      timeFormat: Type.Optional(Type.String({ description: "iso, yyyy/M/d H:mm, yyyy-MM-dd HH:mm:ss, unix-seconds, or unix-milliseconds." })),
      timezoneOffsetMinutes: Type.Optional(Type.Number({ description: "Required to validate timestamps without an explicit zone; JST is 540." })),
      scanRows: Type.Optional(Type.Number({ description: "Rows to profile, from 1 to 100000. Defaults to 10000." })),
    }),
    async execute(_toolCallId, params: {
      path: string;
      delimiter?: string;
      skipRows?: number;
      timeColumn?: string;
      timeFormat?: CsvTimeFormat;
      timezoneOffsetMinutes?: number;
      scanRows?: number;
    }, _signal, _onUpdate, ctx) {
      const inspection = inspectExternalCsv(params, ctx.cwd);
      return toTextToolResult(csvInspectionText(inspection), inspection, {
        tool: "qdash_inspect_timeseries_csv",
        path: inspection.path,
      });
    },
  });

  pi.registerTool({
    name: "qdash_compare_timeseries",
    label: "QDash Compare Timeseries",
    description: "Compare two or more QDash and/or local CSV numeric timeseries on a common time grid. Read-only; reports alignment, correlations, optional shared-period fits, phases, and statistical caveats without inferring causality.",
    promptSnippet: "Compare generic QDash metrics and external CSV sensor timeseries",
    promptGuidelines: [
      "Use qdash_compare_timeseries when comparing multiple QDash metrics, targets, or local CSV sensor logs over time.",
      "For qdash_compare_timeseries local CSV inputs, explicitly specify timestamp format and timezone offset when timestamps have no zone.",
      "Treat qdash_compare_timeseries correlations and shared periods as evidence of association, not proof of causality.",
    ],
    parameters: Type.Object({
      profile: Type.Optional(Type.String({ description: "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise 'default'." })),
      configPath: Type.Optional(Type.String({ description: "Optional path to qdash config.ini." })),
      useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
      chipId: Type.Optional(Type.String({ description: "Chip ID. Defaults to the active/default chip when omitted." })),
      startAt: Type.Optional(Type.String({ description: "Optional common start timestamp as an ISO timestamp with timezone." })),
      endAt: Type.Optional(Type.String({ description: "Optional common end timestamp as an ISO timestamp with timezone." })),
      withinHours: Type.Optional(Type.Number({ description: "QDash lookback when startAt is omitted. Defaults to 168 hours." })),
      useInvestigationContext: Type.Optional(Type.Boolean({ description: "Use missing series/window/transform defaults from the active investigation context. Defaults to true." })),
      qdashSeries: Type.Optional(Type.Array(Type.Object({
        parameter: Type.String({ description: "QDash task-result parameter name." }),
        qid: Type.Optional(Type.String()),
        tag: Type.Optional(Type.String()),
        label: Type.Optional(Type.String({ description: "Unique display label. Defaults to parameter plus qid/returned series." })),
        unit: Type.Optional(Type.String({ description: "Optional output unit override." })),
        scale: Type.Optional(Type.Number({ description: "Multiply QDash values by this factor. Defaults to 1." })),
        offset: Type.Optional(Type.Number({ description: "Add this value after scaling. Defaults to 0." })),
      }), { maxItems: 12 })),
      csvSeries: Type.Optional(Type.Array(Type.Object({
        path: Type.String({ description: "Local CSV path, absolute or relative to the current working directory." }),
        timeColumn: Type.String(),
        valueColumns: Type.Array(Type.Object({
          column: Type.String(),
          label: Type.Optional(Type.String()),
          unit: Type.Optional(Type.String()),
          scale: Type.Optional(Type.Number()),
          offset: Type.Optional(Type.Number()),
        }), { minItems: 1, maxItems: 12 }),
        timeFormat: Type.Optional(Type.String({ description: "iso, yyyy/M/d H:mm, yyyy-MM-dd HH:mm:ss, unix-seconds, or unix-milliseconds. Defaults to iso." })),
        timezoneOffsetMinutes: Type.Optional(Type.Number({ description: "Required for timestamps without an explicit zone; for JST use 540." })),
        delimiter: Type.Optional(Type.String({ description: "Single-character delimiter. Defaults to comma." })),
        skipRows: Type.Optional(Type.Number({ description: "Rows to skip before the header. Defaults to 0." })),
        filters: Type.Optional(Type.Record(Type.String(), Type.Array(Type.String()), { description: "Optional exact-match row filters keyed by column name." })),
      }), { maxItems: 8 })),
      resampleMinutes: Type.Optional(Type.Number({ description: "Common grid interval. Defaults to 1 minute." })),
      smoothingWindowMinutes: Type.Optional(Type.Number({ description: "Centered moving-average window. Zero disables smoothing." })),
      detrend: Type.Optional(Type.String({ description: "none or linear. Defaults to none." })),
      normalize: Type.Optional(Type.String({ description: "none or zscore. Defaults to none." })),
      maxInterpolationGapMinutes: Type.Optional(Type.Number({ description: "Do not interpolate across larger source gaps." })),
      periodSearch: Type.Optional(Type.Object({
        minMinutes: Type.Number(),
        maxMinutes: Type.Number(),
        stepMinutes: Type.Optional(Type.Number()),
      })),
      includeAlignedData: Type.Optional(Type.Boolean({ description: "Include transformed aligned rows in structured details. Defaults to false." })),
    }),
    async execute(_toolCallId, params: ComparisonToolParams, _signal, _onUpdate, ctx) {
      const investigation = params.useInvestigationContext === false ? undefined : dependencies.investigationContext?.();
      const analysis = investigation?.analysis;
      const detrend = params.detrend ?? analysis?.detrend ?? "none";
      const normalize = params.normalize ?? analysis?.normalize ?? "none";
      if (detrend !== "none" && detrend !== "linear") throw new Error("detrend must be 'none' or 'linear'");
      if (normalize !== "none" && normalize !== "zscore") throw new Error("normalize must be 'none' or 'zscore'");
      const csvSpecs = (params.csvSeries ?? investigation?.csvSeries ?? []).map((spec) => ({
        ...spec,
        timezoneOffsetMinutes: spec.timezoneOffsetMinutes ?? investigation?.timezoneOffsetMinutes,
      }));
      const qdashSpecs = (params.qdashSeries ?? investigation?.qdashSeries ?? []).map((spec) => ({
        ...spec,
        tag: spec.tag ?? investigation?.tag,
      }));
      const csv = csvSpecs.flatMap((spec) => loadExternalCsvSeries(spec, ctx.cwd));
      const qdash: NumericTimeseries[] = [];
      let resolvedStartAt = params.startAt ?? investigation?.startAt;
      let resolvedEndAt = params.endAt ?? investigation?.endAt;
      if (qdashSpecs.length > 0) {
        resolvedEndAt = resolvedEndAt ?? new Date().toISOString();
        resolvedStartAt = resolvedStartAt ?? new Date(Date.parse(resolvedEndAt) - (params.withinHours ?? 168) * 3_600_000).toISOString();
        const client = await dependencies.makeClient(params);
        const chipId = await dependencies.defaultChipId(client, params.chipId);
        const fetched = await Promise.all(qdashSpecs.map(async (spec) => {
          const data = await client.getTaskResultsTimeseries({
            chipId,
            parameter: spec.parameter,
            qid: spec.qid,
            tag: spec.tag,
            startAt: resolvedStartAt!,
            endAt: resolvedEndAt!,
          });
          return { spec, points: timeseriesPoints(data) };
        }));
        for (const { spec, points } of fetched) {
          const groups = new Map<string, typeof points>();
          for (const point of points) {
            if (!point.at) continue;
            const group = spec.qid ?? point.series;
            groups.set(group, [...(groups.get(group) ?? []), point]);
          }
          for (const [group, values] of groups) {
            const suffix = spec.qid ? ` q${spec.qid}` : groups.size > 1 ? ` ${group}` : "";
            qdash.push({
              label: spec.label ? groups.size > 1 ? `${spec.label} ${group}` : spec.label : `${spec.parameter}${suffix}`,
              unit: spec.unit ?? values.find((point) => point.unit)?.unit,
              source: "qdash",
              points: values.map((point) => ({
                at: point.at!,
                value: point.value * (spec.scale ?? 1) + (spec.offset ?? 0),
              })),
            });
          }
        }
      }
      const comparison = compareTimeseries([...qdash, ...csv], {
        startAt: resolvedStartAt,
        endAt: resolvedEndAt,
        resampleMinutes: params.resampleMinutes ?? analysis?.resampleMinutes,
        smoothingWindowMinutes: params.smoothingWindowMinutes ?? analysis?.smoothingWindowMinutes,
        detrend,
        normalize,
        maxInterpolationGapMinutes: params.maxInterpolationGapMinutes ?? analysis?.maxInterpolationGapMinutes,
        periodSearch: params.periodSearch ?? analysis?.periodSearch,
        includeAlignedData: params.includeAlignedData,
      });
      return toTextToolResult(timeseriesComparisonText(comparison), comparison, {
        tool: "qdash_compare_timeseries",
        seriesCount: comparison.series.length,
        investigation: investigation?.name,
      });
    },
  });
}
