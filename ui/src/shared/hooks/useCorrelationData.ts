import { useMemo } from 'react';
import { CorrelationDataPoint, StatisticalSummary, ParameterKey } from '../types/analysis';

interface ParameterValue {
  value: number;
  unit: string;
  description: string;
  updated: string;
}

interface UseCorrelationDataOptions {
  chipData: any;
  xParameter: ParameterKey;
  yParameter: ParameterKey;
  enabled?: boolean;
}

/**
 * Generic hook for processing correlation data from chip parameter data
 * Supports both qubit detail page and analysis page correlation views
 */
export function useCorrelationData(options: UseCorrelationDataOptions) {
  const {
    chipData,
    xParameter,
    yParameter,
    enabled = true,
  } = options;

  // Get parameter value for a qubit
  const getParameterValue = (qubit: any, param: string): ParameterValue => {
    if (param === "qid") {
      return {
        value: Number(qubit.qid),
        unit: "",
        description: "Qubit ID",
        updated: "",
      };
    }

    const paramData = qubit?.data?.[param];
    if (!paramData) {
      return {
        value: 0,
        unit: "",
        description: "",
        updated: "",
      };
    }
    
    const value = paramData.value;
    const unit = paramData.unit === "ns" ? "μs" : paramData.unit;

    return {
      value: paramData.unit === "ns" ? value / 1000 : value,
      unit,
      description: paramData.description,
      updated: new Date(paramData.calibrated_at).toLocaleString(),
    };
  };

  // Process correlation data
  const correlationData = useMemo((): CorrelationDataPoint[] => {
    if (!enabled || !chipData?.qubits || !xParameter || !yParameter) return [];

    return Object.entries(chipData.qubits)
      .filter(([_, qubit]: [string, any]) => {
        if (xParameter === "qid" && yParameter === "qid") return true;
        if (xParameter === "qid") return qubit?.data && qubit.data[yParameter];
        if (yParameter === "qid") return qubit?.data && qubit.data[xParameter];
        return qubit?.data && qubit.data[xParameter] && qubit.data[yParameter];
      })
      .map(([qid, qubit]: [string, any]) => {
        const xData = getParameterValue(qubit, xParameter);
        const yData = getParameterValue(qubit, yParameter);

        return {
          qid,
          time: new Date().toISOString(), // Use current time for analysis page
          x: xData.value,
          xUnit: xData.unit,
          xDescription: xData.description,
          y: yData.value,
          yUnit: yData.unit,
          yDescription: yData.description,
        };
      })
      .sort((a, b) => parseInt(a.qid!) - parseInt(b.qid!));
  }, [enabled, chipData, xParameter, yParameter]);

  // Generate plot data with color coding
  const plotData = useMemo(() => {
    if (correlationData.length === 0) return [];

    return correlationData.map((d) => ({
      x: [d.x],
      y: [d.y],
      text: [d.qid],
      textposition: 'top center' as const,
      textfont: { size: 10 },
      mode: 'text+markers' as const,
      type: 'scatter' as const,
      name: `QID: ${d.qid}`,
      marker: correlationData.length > 20 ? {
        size: 10,
        line: { color: 'white', width: 1 },
        opacity: 0.8,
      } : {
        size: 12,
        line: { color: 'white', width: 1 },
      },
      hoverinfo: 'text' as const,
      hovertext: [
        `QID: ${d.qid}<br>` +
        `${xParameter}: ${d.x.toFixed(4)} ${d.xUnit}<br>` +
        `${yParameter}: ${d.y.toFixed(4)} ${d.yUnit}<br>` +
        (d.xDescription ? `Description (X): ${d.xDescription}<br>` : '') +
        (d.yDescription ? `Description (Y): ${d.yDescription}<br>` : ''),
      ],
    }));
  }, [correlationData, xParameter, yParameter]);

  // Calculate statistical summary
  const statistics = useMemo((): StatisticalSummary | null => {
    if (correlationData.length < 2) return null;

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

  // Get available parameters from chip data
  const availableParameters = useMemo(() => {
    if (!chipData?.qubits) return [];
    const params = new Set<string>(['qid']);

    Object.entries(chipData.qubits).forEach(([_, qubit]: [string, any]) => {
      if (qubit?.data) {
        Object.keys(qubit.data).forEach((param) => {
          if (param !== 'qid') {
            params.add(param);
          }
        });
      }
    });

    return Array.from(params).sort();
  }, [chipData]);

  return {
    correlationData,
    plotData,
    statistics,
    availableParameters,
    isLoading: false, // This hook processes existing data
    error: null as any, // Fix TypeScript error
  };
}