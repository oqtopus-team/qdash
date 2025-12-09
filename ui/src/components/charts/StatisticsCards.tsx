import type { StatisticalSummary } from "@/types/analysis";

interface StatisticsCardsProps {
  statistics: StatisticalSummary;
  xParameter: string;
  yParameter: string;
  xUnit?: string;
  yUnit?: string;
}

/**
 * Reusable statistical summary cards for correlation analysis
 */
export function StatisticsCards({
  statistics,
  xParameter,
  yParameter,
  xUnit = "",
  yUnit = "",
}: StatisticsCardsProps) {
  const getCorrelationStrength = (correlation: number) => {
    const abs = Math.abs(correlation);
    if (abs >= 0.8) return { strength: "Very Strong", color: "text-success" };
    if (abs >= 0.6) return { strength: "Strong", color: "text-success" };
    if (abs >= 0.4) return { strength: "Moderate", color: "text-warning" };
    if (abs >= 0.2) return { strength: "Weak", color: "text-warning" };
    return { strength: "Very Weak", color: "text-error" };
  };

  const correlationInfo =
    statistics.correlation !== undefined
      ? getCorrelationStrength(statistics.correlation)
      : null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* X-axis Statistics */}
      <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
        <h3 className="font-medium mb-4 flex items-center gap-2">
          <span className="text-primary">X:</span> {xParameter} Statistics
        </h3>
        <div className="space-y-4">
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-title">Mean</div>
            <div className="stat-value text-lg">
              {statistics.xMean.toFixed(6)}
              {xUnit && <span className="text-sm ml-1">{xUnit}</span>}
            </div>
          </div>
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-title">Std Deviation</div>
            <div className="stat-value text-lg">
              {statistics.xStd.toFixed(6)}
              {xUnit && <span className="text-sm ml-1">{xUnit}</span>}
            </div>
          </div>
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-title">Range</div>
            <div className="stat-value text-sm flex items-center gap-2">
              <span>{statistics.xMin.toFixed(6)}</span>
              <span className="text-base-content/50">to</span>
              <span>{statistics.xMax.toFixed(6)}</span>
              {xUnit && <span className="text-xs ml-1">{xUnit}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Y-axis Statistics */}
      <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
        <h3 className="font-medium mb-4 flex items-center gap-2">
          <span className="text-secondary">Y:</span> {yParameter} Statistics
        </h3>
        <div className="space-y-4">
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-title">Mean</div>
            <div className="stat-value text-lg">
              {statistics.yMean.toFixed(6)}
              {yUnit && <span className="text-sm ml-1">{yUnit}</span>}
            </div>
          </div>
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-title">Std Deviation</div>
            <div className="stat-value text-lg">
              {statistics.yStd.toFixed(6)}
              {yUnit && <span className="text-sm ml-1">{yUnit}</span>}
            </div>
          </div>
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-title">Range</div>
            <div className="stat-value text-sm flex items-center gap-2">
              <span>{statistics.yMin.toFixed(6)}</span>
              <span className="text-base-content/50">to</span>
              <span>{statistics.yMax.toFixed(6)}</span>
              {yUnit && <span className="text-xs ml-1">{yUnit}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Correlation Statistics */}
      <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
        <h3 className="font-medium mb-4 flex items-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-4 h-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
          Correlation Analysis
        </h3>
        <div className="space-y-4">
          {statistics.correlation !== undefined && (
            <div className="stat bg-base-200 rounded-lg">
              <div className="stat-title">Correlation Coefficient</div>
              <div className="stat-value text-lg">
                {statistics.correlation.toFixed(6)}
              </div>
              {correlationInfo && (
                <div className="stat-desc mt-2">
                  <div
                    className={`badge badge-sm ${
                      correlationInfo.color.includes("success")
                        ? "badge-success"
                        : correlationInfo.color.includes("warning")
                          ? "badge-warning"
                          : "badge-error"
                    }`}
                  >
                    {correlationInfo.strength}
                  </div>
                </div>
              )}
            </div>
          )}
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-title">Data Points</div>
            <div className="stat-value text-lg">{statistics.dataPoints}</div>
          </div>
          {statistics.correlation !== undefined && (
            <div className="stat bg-base-200 rounded-lg">
              <div className="stat-title">R²</div>
              <div className="stat-value text-lg">
                {(statistics.correlation ** 2).toFixed(6)}
              </div>
              <div className="stat-desc mt-1 text-xs">
                Coefficient of determination
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
