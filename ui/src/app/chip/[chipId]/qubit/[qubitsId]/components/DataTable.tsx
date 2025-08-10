import { useMemo, useState } from "react";
import { SortDirection, TimeSeriesDataPoint } from "../types";

interface DataTableProps {
  data: TimeSeriesDataPoint[];
  title: string;
  qubitId?: string;
  onDownloadCSV?: () => void;
  rowsPerPage?: number;
}

export function DataTable({
  data,
  title,
  qubitId,
  onDownloadCSV,
  rowsPerPage = 50,
}: DataTableProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const sortedData = useMemo(() => {
    return [...data].sort((a, b) => {
      const direction = sortDirection === "asc" ? 1 : -1;
      return direction * a.time.localeCompare(b.time);
    });
  }, [data, sortDirection]);

  const paginatedData = useMemo(() => {
    const startIndex = (currentPage - 1) * rowsPerPage;
    return sortedData.slice(startIndex, startIndex + rowsPerPage);
  }, [sortedData, currentPage, rowsPerPage]);

  const totalPages = Math.ceil(sortedData.length / rowsPerPage);

  const handleSort = () => {
    setSortDirection(prev => prev === "asc" ? "desc" : "asc");
  };

  return (
    <div className="card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-4">
          <h2 className="text-2xl font-semibold">
            {title} {qubitId && `- Qubit ${qubitId}`}
          </h2>
          {onDownloadCSV && (
            <button
              className="btn btn-sm btn-outline gap-2"
              onClick={onDownloadCSV}
              disabled={!data.length}
              title="Download all data as CSV"
              aria-label="Download CSV file"
            >
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
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Download CSV
            </button>
          )}
        </div>
        <div className="text-sm text-base-content/70">
          {sortedData.length} entries
        </div>
      </div>

      <div className="overflow-x-auto" style={{ minHeight: "400px" }}>
        <table className="table table-compact table-zebra w-full border border-base-300 bg-base-100">
          <thead>
            <tr>
              <th
                className="text-left bg-base-200 cursor-pointer hover:bg-base-300"
                onClick={handleSort}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleSort();
                  }
                }}
                aria-label={`Sort by time ${sortDirection === 'asc' ? 'descending' : 'ascending'}`}
              >
                <div className="flex items-center gap-1">
                  Time
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className={`w-4 h-4 transition-transform ${
                      sortDirection === "desc" ? "rotate-180" : ""
                    }`}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M18 15l-6-6-6 6" />
                  </svg>
                </div>
              </th>
              <th className="text-center bg-base-200">Value</th>
              <th className="text-center bg-base-200">Error</th>
              <th className="text-center bg-base-200">Unit</th>
            </tr>
          </thead>
          <tbody>
            {paginatedData.map((row, index) => (
              <tr key={`${row.time}-${index}`}>
                <td className="text-left">{row.time}</td>
                <td className="text-center">
                  {typeof row.value === "number"
                    ? row.value.toFixed(4)
                    : row.value}
                </td>
                <td className="text-center">
                  {row.error !== undefined
                    ? `±${row.error.toFixed(4)}`
                    : "-"}
                </td>
                <td className="text-center">{row.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-between items-center mt-4">
            <div className="text-sm text-base-content/70">
              Showing {Math.min(rowsPerPage, sortedData.length)} of{" "}
              {sortedData.length} entries
            </div>
            <div className="join">
              <button
                className="join-item btn btn-sm"
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                aria-label="Go to previous page"
              >
                Previous
              </button>
              <button 
                className="join-item btn btn-sm btn-disabled"
                aria-label={`Page ${currentPage} of ${totalPages}`}
              >
                Page {currentPage} of {totalPages}
              </button>
              <button
                className="join-item btn btn-sm"
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                aria-label="Go to next page"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}