import { useMemo } from 'react';
import { useFetchTimeseriesTaskResultByTagAndParameterAndQid } from "@/client/chip/chip";
import { ParameterKey, TagKey, TimeRangeState, CorrelationDataPoint, StatisticalSummary } from '../types';
import { OutputParameterModel } from "@/schemas";

interface UseQubitCorrelationOptions {
  chipId: string;
  qubitId: string;
  xParameter: ParameterKey;
  yParameter: ParameterKey;
  tag: TagKey;
  timeRange: TimeRangeState;
  enabled?: boolean;
}

/**
 * Custom hook for fetching and processing qubit correlation data
 */
export function useQubitCorrelation(options: UseQubitCorrelationOptions) {
  const {
    chipId,
    qubitId,
    xParameter,
    yParameter,
    tag,
    timeRange,
    enabled = true,
  } = options;

  // Fetch X-axis parameter data
  const {
    data: xAxisData,
    isLoading: isLoadingX,
    error: errorX,
  } = useFetchTimeseriesTaskResultByTagAndParameterAndQid(
    chipId,
    xParameter,
    qubitId,
    {
      tag,
      start_at: timeRange.startAt,
      end_at: timeRange.endAt,
    },
    {
      query: {
        enabled: Boolean(enabled && chipId && xParameter && tag && qubitId),
        staleTime: 30000,
      },
    },
  );

  // Fetch Y-axis parameter data
  const {
    data: yAxisData,
    isLoading: isLoadingY,
    error: errorY,
  } = useFetchTimeseriesTaskResultByTagAndParameterAndQid(
    chipId,
    yParameter,
    qubitId,
    {
      tag,
      start_at: timeRange.startAt,
      end_at: timeRange.endAt,
    },
    {
      query: {
        enabled: Boolean(enabled && chipId && yParameter && tag && qubitId),
        staleTime: 30000,
      },
    },
  );

  // Process correlation data
  const correlationData = useMemo((): CorrelationDataPoint[] | null => {
    if (!xAxisData?.data?.data || !yAxisData?.data?.data) return null;

    const xQubitData = xAxisData.data.data[qubitId];
    const yQubitData = yAxisData.data.data[qubitId];

    if (!Array.isArray(xQubitData) || !Array.isArray(yQubitData)) return null;

    // Create maps for efficient time-based lookup
    const xDataMap = new Map<string, OutputParameterModel>();
    const yDataMap = new Map<string, OutputParameterModel>();

    xQubitData.forEach((point: OutputParameterModel) => {
      if (point.calibrated_at) {
        xDataMap.set(point.calibrated_at, point);
      }
    });

    yQubitData.forEach((point: OutputParameterModel) => {
      if (point.calibrated_at) {
        yDataMap.set(point.calibrated_at, point);
      }
    });

    // Find common time points
    const commonTimes = Array.from(xDataMap.keys()).filter(time => yDataMap.has(time));
    
    if (commonTimes.length === 0) return null;

    // Create correlation data points
    const correlatedData = commonTimes
      .map(time => {
        const xPoint = xDataMap.get(time)!;
        const yPoint = yDataMap.get(time)!;
        
        const xValue = typeof xPoint.value === 'number' 
          ? xPoint.value 
          : parseFloat(String(xPoint.value)) || 0;
        const yValue = typeof yPoint.value === 'number' 
          ? yPoint.value 
          : parseFloat(String(yPoint.value)) || 0;

        return {
          time,
          x: xValue,
          y: yValue,
          xUnit: xPoint.unit || 'a.u.',
          yUnit: yPoint.unit || 'a.u.',
          xDescription: xPoint.description || '',
          yDescription: yPoint.description || '',
        };
      })
      .sort((a, b) => a.time.localeCompare(b.time));

    return correlatedData;
  }, [xAxisData?.data?.data, yAxisData?.data?.data, qubitId]);

  // Generate plot data with time progression coloring
  const plotData = useMemo(() => {
    if (!correlationData || correlationData.length === 0) return [];

    // Create color gradient based on time progression
    const colors = correlationData.map((_, index) => {
      const ratio = correlationData.length > 1 ? index / (correlationData.length - 1) : 0;
      const r = Math.floor(ratio * 255);
      const b = Math.floor((1 - ratio) * 255);
      return `rgb(${r}, 100, ${b})`;
    });

    return [{
      x: correlationData.map(d => d.x),
      y: correlationData.map(d => d.y),
      mode: 'markers+lines' as const,
      type: 'scatter' as const,
      name: `Qubit ${qubitId} Correlation`,
      line: { width: 2, color: 'rgba(59, 130, 246, 0.6)' },
      marker: {
        size: 8,
        color: colors,
        colorscale: 'Cividis' as const, // Color-blind friendly
        showscale: true,
        colorbar: {
          title: 'Time Progression',
          titleside: 'right' as const,
          thickness: 15,
          len: 0.5,
        },
        line: { color: 'white', width: 1 },
      },
      customdata: correlationData.map(d => [
        d.time,
        `${xParameter}: ${d.x.toFixed(6)} ${d.xUnit}`,
        `${yParameter}: ${d.y.toFixed(6)} ${d.yUnit}`,
      ]),
      hovertemplate:
        'Time: %{customdata[0]}<br>' +
        '%{customdata[1]}<br>' +
        '%{customdata[2]}<br>' +
        '<extra></extra>',
    }];
  }, [correlationData, xParameter, yParameter, qubitId]);

  // Calculate statistical summary
  const statistics = useMemo((): StatisticalSummary | null => {
    if (!correlationData || correlationData.length < 2) return null;

    const xValues = correlationData.map(d => d.x);
    const yValues = correlationData.map(d => d.y);
    const n = xValues.length;

    // Calculate means
    const xMean = xValues.reduce((sum, x) => sum + x, 0) / n;
    const yMean = yValues.reduce((sum, y) => sum + y, 0) / n;
    
    // Calculate correlation coefficient
    const numerator = correlationData.reduce((sum, d) => sum + (d.x - xMean) * (d.y - yMean), 0);
    const xVariance = xValues.reduce((sum, x) => sum + Math.pow(x - xMean, 2), 0);
    const yVariance = yValues.reduce((sum, y) => sum + Math.pow(y - yMean, 2), 0);
    
    const correlation = numerator / Math.sqrt(xVariance * yVariance);

    return {
      correlation: isNaN(correlation) ? 0 : correlation,
      xMean,
      yMean,
      xStd: Math.sqrt(xVariance / n),
      yStd: Math.sqrt(yVariance / n),
      xMin: Math.min(...xValues),
      xMax: Math.max(...xValues),
      yMin: Math.min(...yValues),
      yMax: Math.max(...yValues),
      dataPoints: n,
    };
  }, [correlationData]);

  const isLoading = isLoadingX || isLoadingY;
  const error = errorX || errorY;

  return {
    correlationData,
    plotData,
    statistics,
    isLoading,
    error,
  };
}