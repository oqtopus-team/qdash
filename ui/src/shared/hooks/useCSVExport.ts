import { useCallback } from "react";
import {
  TimeSeriesDataPoint,
  CorrelationDataPoint,
  CSVExportOptions,
} from "../types/analysis";

/**
 * Custom hook for CSV export functionality
 * Supports both time series and correlation data exports
 */
export function useCSVExport() {
  // Generic CSV export function
  const exportToCSV = useCallback((options: CSVExportOptions) => {
    const { filename, headers, data } = options;

    // Create CSV content
    const csvContent = [
      headers.join(","),
      ...data.map((row) =>
        row
          .map((cell) => {
            // Handle numbers, strings, and special characters
            const cellStr = String(cell);
            // Wrap in quotes if contains comma, newline, or quote
            return cellStr.includes(",") ||
              cellStr.includes("\n") ||
              cellStr.includes('"')
              ? `"${cellStr.replace(/"/g, '""')}"`
              : cellStr;
          })
          .join(","),
      ),
    ].join("\n");

    // Create and trigger download
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, []);

  // Export time series data
  const exportTimeSeriesCSV = useCallback(
    (
      data: TimeSeriesDataPoint[],
      parameter: string,
      chipId?: string,
      tag?: string,
    ) => {
      if (!data || data.length === 0) return;

      const headers = ["QID", "Time", "Parameter", "Value", "Error", "Unit"];
      const rows = data.map((point) => [
        point.qid || "",
        point.time,
        parameter,
        String(point.value),
        String(point.error || ""),
        point.unit,
      ]);

      // Sort rows by QID and time
      rows.sort((a, b) => {
        const qidCompare = parseInt(a[0]) - parseInt(b[0]);
        if (qidCompare !== 0) return qidCompare;
        return a[1].localeCompare(b[1]);
      });

      const timestamp = new Date()
        .toISOString()
        .slice(0, 19)
        .replace(/[:-]/g, "");
      const filename = `timeseries_${chipId || "unknown"}_${parameter}_${tag || "data"}_${timestamp}.csv`;

      exportToCSV({ filename, headers, data: rows });
    },
    [exportToCSV],
  );

  // Export correlation data
  const exportCorrelationCSV = useCallback(
    (
      data: CorrelationDataPoint[],
      xParameter: string,
      yParameter: string,
      chipId?: string,
      qubitId?: string,
    ) => {
      if (!data || data.length === 0) return;

      const headers = [
        "QID",
        "Time",
        `${xParameter}_Value`,
        `${xParameter}_Unit`,
        `${yParameter}_Value`,
        `${yParameter}_Unit`,
      ];

      const rows = data.map((point) => [
        point.qid || qubitId || "",
        point.time,
        String(point.x),
        point.xUnit,
        String(point.y),
        point.yUnit,
      ]);

      const timestamp = new Date()
        .toISOString()
        .slice(0, 19)
        .replace(/[:-]/g, "");
      const filename = `correlation_${chipId || "unknown"}_${qubitId || "multi"}_${xParameter}_vs_${yParameter}_${timestamp}.csv`;

      exportToCSV({ filename, headers, data: rows });
    },
    [exportToCSV],
  );

  return {
    exportToCSV,
    exportTimeSeriesCSV,
    exportCorrelationCSV,
  };
}
