import { StatisticalSummary } from "../types";

interface StatisticsCardsProps {
  statistics: StatisticalSummary;
  xParameter: string;
  yParameter: string;
}

function getCorrelationStrength(correlation: number): {
  label: string;
  className: string;
} {
  const absCorr = Math.abs(correlation);
  if (absCorr > 0.7) {
    return { label: "Strong", className: "text-success" };
  } else if (absCorr > 0.3) {
    return { label: "Moderate", className: "text-warning" };
  } else {
    return { label: "Weak", className: "text-base-content" };
  }
}

export function StatisticsCards({ statistics, xParameter, yParameter }: StatisticsCardsProps) {
  const correlationStrength = getCorrelationStrength(statistics.correlation);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Correlation Analysis */}
      <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
        <h3 className="font-medium mb-4 flex items-center gap-2">
          <span className="text-primary" aria-hidden="true">📊</span> 
          Correlation Analysis
        </h3>
        <div className="space-y-3">
          <div className="stat bg-base-200 rounded-lg p-3">
            <div className="stat-title text-xs">Correlation Coefficient</div>
            <div className={`stat-value text-lg ${correlationStrength.className}`}>
              {statistics.correlation.toFixed(4)}
            </div>
            <div className="stat-desc text-xs">
              {correlationStrength.label} correlation
            </div>
          </div>
          <div className="stat bg-base-200 rounded-lg p-3">
            <div className="stat-title text-xs">Data Points</div>
            <div className="stat-value text-lg">{statistics.dataPoints}</div>
          </div>
        </div>
      </div>

      {/* X Parameter Statistics */}
      <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
        <h3 className="font-medium mb-4 flex items-center gap-2">
          <span className="text-primary">X:</span> {xParameter} Statistics
        </h3>
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Mean:</span>
            <span>{statistics.xMean.toFixed(6)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Std Dev:</span>
            <span>{statistics.xStd.toFixed(6)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Min:</span>
            <span>{statistics.xMin.toFixed(6)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Max:</span>
            <span>{statistics.xMax.toFixed(6)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Range:</span>
            <span>{(statistics.xMax - statistics.xMin).toFixed(6)}</span>
          </div>
        </div>
      </div>

      {/* Y Parameter Statistics */}
      <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
        <h3 className="font-medium mb-4 flex items-center gap-2">
          <span className="text-secondary">Y:</span> {yParameter} Statistics
        </h3>
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Mean:</span>
            <span>{statistics.yMean.toFixed(6)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Std Dev:</span>
            <span>{statistics.yStd.toFixed(6)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Min:</span>
            <span>{statistics.yMin.toFixed(6)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Max:</span>
            <span>{statistics.yMax.toFixed(6)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Range:</span>
            <span>{(statistics.yMax - statistics.yMin).toFixed(6)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}