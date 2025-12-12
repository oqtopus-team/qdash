import type { ReactNode } from "react";
import { useState, useMemo, useEffect } from "react";

import { EmptyState } from "./EmptyState";

interface Column {
  key: string;
  label: string;
  sortable?: boolean;
  className?: string;
  // Using any here to maintain compatibility with existing render functions
  // that have specific value types (number, string, etc.)
  // biome-ignore lint: required for flexible column rendering
  render?: (value: any, row: any) => ReactNode;
}

// DataRow uses any to allow for flexible data structures from various sources
// biome-ignore lint: required for flexible data structures
type DataRow = Record<string, any>;

interface DataTableProps {
  title: string;
  data: DataRow[];
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
  useEffect(() => {
    setCurrentPage(1);
  }, [filter]);

  return (
    <div
      className={`card bg-base-100 shadow-xl rounded-xl p-4 sm:p-8 border border-base-300 ${className}`}
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4 sm:mb-6">
        <div className="flex flex-wrap items-center gap-2 sm:gap-4">
          <h2 className="text-lg sm:text-2xl font-semibold">{title}</h2>
          {actions}
        </div>

        {/* Search and Info */}
        <div className="flex items-center gap-2 sm:gap-4 w-full sm:w-auto">
          {searchable && (
            <div className="form-control flex-1 sm:flex-none">
              <input
                type="text"
                placeholder={searchPlaceholder}
                className="input input-bordered input-xs sm:input-sm w-full sm:w-64"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
          )}
          <div className="text-xs sm:text-sm text-base-content/70 whitespace-nowrap">
            {filter
              ? `${processedData.length} filtered`
              : `${data.length} total`}
          </div>
        </div>
      </div>

      {/* Table */}
      <div
        className="overflow-x-auto -mx-4 sm:mx-0"
        style={{ minHeight: "300px" }}
      >
        {processedData.length === 0 ? (
          <EmptyState
            title={filter ? "No results found" : emptyMessage}
            description={
              filter ? "Try adjusting your search criteria." : undefined
            }
            emoji={filter ? "magnifying-glass" : "empty"}
            size="sm"
          />
        ) : (
          <>
            <table className="table table-xs sm:table-compact table-zebra w-full border border-base-300 bg-base-100">
              <thead className="sticky top-0 bg-base-200">
                <tr>
                  {columns.map((column) => (
                    <th
                      key={column.key}
                      className={`${column.className || "text-center"} text-xs sm:text-sm px-2 sm:px-4 ${
                        column.sortable
                          ? "cursor-pointer hover:bg-base-300"
                          : ""
                      }`}
                      onClick={() => column.sortable && handleSort(column.key)}
                    >
                      <div className="flex items-center gap-1 justify-center">
                        <span className="truncate max-w-[80px] sm:max-w-none">
                          {column.label}
                        </span>
                        {column.sortable && sortField === column.key && (
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className={`w-3 h-3 sm:w-4 sm:h-4 transition-transform flex-shrink-0 ${
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
                  <tr
                    key={index}
                    className="transition-colors hover:bg-base-200/80"
                  >
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={`${column.className || "text-center"} text-xs sm:text-sm px-2 sm:px-4`}
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
              <div className="flex flex-col sm:flex-row justify-between items-center gap-2 mt-4 px-4 sm:px-0">
                <div className="text-xs sm:text-sm text-base-content/70">
                  {Math.min(pageSize, processedData.length)} /{" "}
                  {processedData.length}
                </div>
                <div className="join">
                  <button
                    className="join-item btn btn-xs sm:btn-sm"
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                  >
                    Prev
                  </button>
                  <button className="join-item btn btn-xs sm:btn-sm btn-disabled">
                    {currentPage}/{totalPages}
                  </button>
                  <button
                    className="join-item btn btn-xs sm:btn-sm"
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
