"use client";

import { Download } from "lucide-react";

interface MetricConfig {
  key: string;
  title: string;
  unit: string;
  scale: number;
}

interface MetricEntry {
  value: number | null;
  stddev?: number | null;
}

interface MetricsYamlDownloadButtonProps {
  chipId: string;
  metricData: {
    [entityId: string]: MetricEntry;
  } | null;
  metricConfig: MetricConfig | undefined;
  selectionMode: "latest" | "best" | "average";
  timeRange: "1d" | "7d" | "30d" | "custom";
  disabled?: boolean;
}

function escapeYamlString(value: string): string {
  if (/[:#\[\]{}&*!|>'"%@`]/.test(value) || value.trim() !== value) {
    return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
  return `"${value}"`;
}

function buildYaml(
  chipId: string,
  metricConfig: MetricConfig,
  selectionMode: string,
  timeRange: string,
  metricData: { [entityId: string]: MetricEntry },
): string {
  const timestamp = new Date().toISOString();
  const hasStddev =
    selectionMode === "average" &&
    Object.values(metricData).some(
      (v) => v.stddev !== null && v.stddev !== undefined,
    );

  const lines: string[] = [
    `chip_id: ${escapeYamlString(chipId)}`,
    `metric: ${metricConfig.key}`,
    `title: ${escapeYamlString(metricConfig.title)}`,
    `unit: ${escapeYamlString(metricConfig.unit)}`,
    `selection_mode: ${selectionMode}`,
    `time_range: ${timeRange}`,
    `timestamp: ${escapeYamlString(timestamp)}`,
    `data:`,
  ];

  const entries = Object.entries(metricData)
    .filter(([, v]) => v.value !== null)
    .sort(([a], [b]) => {
      const numA = parseFloat(a);
      const numB = parseFloat(b);
      if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
      return a.localeCompare(b);
    });

  if (hasStddev) {
    for (const [entityId, { value, stddev }] of entries) {
      lines.push(`  ${escapeYamlString(entityId)}:`);
      lines.push(`    value: ${value}`);
      lines.push(
        `    stddev: ${stddev != null && isFinite(stddev) ? stddev : "null"}`,
      );
    }
  } else {
    for (const [entityId, { value }] of entries) {
      lines.push(`  ${escapeYamlString(entityId)}: ${value}`);
    }
  }

  return lines.join("\n") + "\n";
}

export function MetricsYamlDownloadButton({
  chipId,
  metricData,
  metricConfig,
  selectionMode,
  timeRange,
  disabled = false,
}: MetricsYamlDownloadButtonProps) {
  const handleDownload = () => {
    if (!chipId || !metricData || !metricConfig) return;

    const yaml = buildYaml(
      chipId,
      metricConfig,
      selectionMode,
      timeRange,
      metricData,
    );

    const blob = new Blob([yaml], { type: "text/yaml;charset=utf-8" });

    const now = new Date();
    const timestamp = now
      .toISOString()
      .slice(0, 19)
      .replace(/[-:T]/g, "")
      .replace(/(\d{8})(\d{6})/, "$1_$2");
    const filename = `metrics_${metricConfig.key}_${chipId}_${timestamp}.yaml`;

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  return (
    <button
      onClick={handleDownload}
      disabled={disabled || !chipId || !metricData || !metricConfig}
      className="btn btn-outline btn-sm gap-2"
      title="Download selected metric data as YAML"
    >
      <Download className="h-4 w-4" />
      <span className="hidden sm:inline">YAML</span>
    </button>
  );
}
