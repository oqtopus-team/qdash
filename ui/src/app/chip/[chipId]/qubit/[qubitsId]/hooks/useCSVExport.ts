import { useCallback } from 'react';
import { CSVExportData } from '../types';

/**
 * Custom hook for CSV export functionality
 */
export function useCSVExport() {
  const downloadCSV = useCallback((data: CSVExportData) => {
    if (!data.rows.length) {
      console.warn('No data available for CSV export');
      return;
    }

    try {
      // Create CSV content
      const csvContent = [
        data.headers.join(','),
        ...data.rows.map(row => 
          row.map(cell => {
            // Escape quotes and wrap in quotes if contains comma, quote, or newline
            const escaped = String(cell).replace(/"/g, '""');
            return /[,"\n\r]/.test(escaped) ? `"${escaped}"` : escaped;
          }).join(',')
        ),
      ].join('\n');

      // Create blob and download
      const blob = new Blob([csvContent], { 
        type: 'text/csv;charset=utf-8;' 
      });
      
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = data.filename;
      link.style.display = 'none';
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Clean up the URL object
      setTimeout(() => URL.revokeObjectURL(url), 100);
      
    } catch (error) {
      console.error('Failed to download CSV:', error);
    }
  }, []);

  const createTimeSeriesCSV = useCallback((
    timeseriesData: any,
    qubitId: string,
    selectedParameter: string,
    selectedTag: string
  ): CSVExportData => {
    const headers = ['Time', 'Parameter', 'Value', 'Error', 'Unit'];
    const rows: string[][] = [];

    const qubitData = timeseriesData?.data?.data?.[qubitId];
    if (Array.isArray(qubitData)) {
      qubitData.forEach((point: any) => {
        rows.push([
          point.calibrated_at || '',
          selectedParameter,
          String(point.value || ''),
          String(point.error || ''),
          point.unit || 'a.u.',
        ]);
      });
    }

    // Sort rows by time
    rows.sort((a, b) => a[0].localeCompare(b[0]));

    const timestamp = new Date()
      .toISOString()
      .slice(0, 19)
      .replace(/[:-]/g, '');

    return {
      headers,
      rows,
      filename: `qubit_${qubitId}_timeseries_${selectedParameter}_${selectedTag}_${timestamp}.csv`,
    };
  }, []);

  const createCorrelationCSV = useCallback((
    correlationData: any[],
    qubitId: string,
    xAxis: string,
    yAxis: string
  ): CSVExportData => {
    const headers = ['Time', `${xAxis}_Value`, `${xAxis}_Unit`, `${yAxis}_Value`, `${yAxis}_Unit`];
    const rows: string[][] = [];

    if (correlationData) {
      correlationData.forEach((point) => {
        rows.push([
          new Date(point.time).toISOString(),
          String(point.x),
          point.xUnit,
          String(point.y),
          point.yUnit,
        ]);
      });
    }

    const timestamp = new Date()
      .toISOString()
      .slice(0, 19)
      .replace(/[:-]/g, '');

    return {
      headers,
      rows,
      filename: `qubit_${qubitId}_correlation_${xAxis}_vs_${yAxis}_${timestamp}.csv`,
    };
  }, []);

  return {
    downloadCSV,
    createTimeSeriesCSV,
    createCorrelationCSV,
  };
}