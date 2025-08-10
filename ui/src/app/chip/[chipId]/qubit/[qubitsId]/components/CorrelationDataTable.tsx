import { CorrelationDataPoint } from "../types";

interface CorrelationDataTableProps {
  data: CorrelationDataPoint[];
  qubitId: string;
  xParameter: string;
  yParameter: string;
}

export function CorrelationDataTable({
  data,
  qubitId,
  xParameter,
  yParameter,
}: CorrelationDataTableProps) {
  if (!data || data.length === 0) {
    return null;
  }

  return (
    <div className="card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-semibold">
          Correlation Data Table - Qubit {qubitId}
        </h2>
        <div className="text-sm text-base-content/70">
          {data.length} data points
        </div>
      </div>
      <div className="overflow-x-auto max-h-96">
        <table className="table table-compact table-zebra w-full border border-base-300 bg-base-100">
          <thead className="sticky top-0 bg-base-200">
            <tr>
              <th className="text-center">Time</th>
              <th className="text-center">{xParameter}</th>
              <th className="text-center">{yParameter}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row, index) => (
              <tr key={`${row.time}-${index}`}>
                <td className="text-center text-xs">
                  <div>
                    {new Date(row.time).toLocaleDateString()}
                  </div>
                  <div className="text-base-content/70">
                    {new Date(row.time).toLocaleTimeString()}
                  </div>
                </td>
                <td className="text-center">
                  <div>
                    {row.x.toFixed(6)}
                  </div>
                  <div className="text-xs text-base-content/70">
                    {row.xUnit}
                  </div>
                </td>
                <td className="text-center">
                  <div>
                    {row.y.toFixed(6)}
                  </div>
                  <div className="text-xs text-base-content/70">
                    {row.yUnit}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}