import { useState, useMemo, ReactNode } from "react";

interface Column {
  key: string;
  label: string;
  sortable?: boolean;
  className?: string;
  render?: (value: any, row: any) => ReactNode;
}

interface DataTableProps {
  title: string;
  data: any[];
  columns: Column[];
  searchable?: boolean;
  searchPlaceholder?: string;
  searchKey?: string;
  pageSize?: number;
  actions?: ReactNode;
  className?: string;
  emptyMessage?: string;
}

type SortDirection = "asc" | "desc";

/**
 * Reusable data table component with sorting, filtering, and pagination
 */
export function DataTable({
  title,
  data,
  columns,
  searchable = false,
  searchPlaceholder = "Search...",
  searchKey = "",
  pageSize = 50,
  actions,
  className = "",
  emptyMessage = "No data available",
}: DataTableProps) {
  const [filter, setFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<string>("");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // Handle sort
  const handleSort = (field: string) => {
    if (!columns.find((col) => col.key === field)?.sortable) return;

    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
    setCurrentPage(1);
  };

  // Filtered and sorted data
  const processedData = useMemo(() => {
    let filtered = data;

    // Apply search filter
    if (searchable && filter && searchKey) {
      filtered = data.filter((row) =>
        String(row[searchKey]).toLowerCase().includes(filter.toLowerCase()),
      );
    }

    // Apply sorting
    if (sortField) {
      filtered = [...filtered].sort((a, b) => {
        const aVal = a[sortField];
        const bVal = b[sortField];
        const direction = sortDirection === "asc" ? 1 : -1;

        // Handle different data types
        if (typeof aVal === "number" && typeof bVal === "number") {
          return direction * (aVal - bVal);
        }

        return direction * String(aVal).localeCompare(String(bVal));
      });
    }

    return filtered;
  }, [data, filter, sortField, sortDirection, searchable, searchKey]);

  // Pagination
  const totalPages = Math.ceil(processedData.length / pageSize);
  const paginatedData = processedData.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );

  // Reset page when filter changes
  useMemo(() => {
    setCurrentPage(1);
  }, [filter]);

  return (
    <div
      className={`card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300 ${className}`}
    >
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-4">
          <h2 className="text-2xl font-semibold">{title}</h2>
          {actions}
        </div>

        {/* Search and Info */}
        <div className="flex items-center gap-4">
          {searchable && (
            <div className="form-control">
              <input
                type="text"
                placeholder={searchPlaceholder}
                className="input input-bordered input-sm w-64"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
          )}
          <div className="text-sm text-base-content/70">
            {filter
              ? `${processedData.length} filtered`
              : `${data.length} total`}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto" style={{ minHeight: "400px" }}>
        {processedData.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-base-content/50">
            {emptyMessage}
          </div>
        ) : (
          <>
            <table className="table table-compact table-zebra w-full border border-base-300 bg-base-100">
              <thead className="sticky top-0 bg-base-200">
                <tr>
                  {columns.map((column) => (
                    <th
                      key={column.key}
                      className={`${column.className || "text-center"} ${
                        column.sortable
                          ? "cursor-pointer hover:bg-base-300"
                          : ""
                      }`}
                      onClick={() => column.sortable && handleSort(column.key)}
                    >
                      <div className="flex items-center gap-1 justify-center">
                        {column.label}
                        {column.sortable && sortField === column.key && (
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
                          >
                            <path d="M18 15l-6-6-6 6" />
                          </svg>
                        )}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paginatedData.map((row, index) => (
                  <tr key={index}>
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={column.className || "text-center"}
                      >
                        {column.render
                          ? column.render(row[column.key], row)
                          : String(row[column.key] || "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex justify-between items-center mt-4">
                <div className="text-sm text-base-content/70">
                  Showing {Math.min(pageSize, processedData.length)} of{" "}
                  {processedData.length} entries
                </div>
                <div className="join">
                  <button
                    className="join-item btn btn-sm"
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                  >
                    Previous
                  </button>
                  <button className="join-item btn btn-sm btn-disabled">
                    Page {currentPage} of {totalPages}
                  </button>
                  <button
                    className="join-item btn btn-sm"
                    onClick={() =>
                      setCurrentPage((p) => Math.min(totalPages, p + 1))
                    }
                    disabled={currentPage === totalPages}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
