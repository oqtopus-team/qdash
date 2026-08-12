import type { ReactNode } from "react";
import { useMemo } from "react";

import {
  columnFilteringFeature,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";

import type { ColumnDef } from "@tanstack/react-table";

import { EmptyState } from "./EmptyState";

interface DataTableColumn<TData extends object> {
  key: string;
  label: string;
  sortable?: boolean;
  className?: string;
  // Cell values vary by dynamic analysis columns; row data remains strongly typed.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  render?: (value: any, row: TData) => ReactNode;
}

interface DataTableProps<TData extends object> {
  title: string;
  data: TData[];
  columns: DataTableColumn<TData>[];
  searchable?: boolean;
  searchPlaceholder?: string;
  searchKey?: string;
  pageSize?: number;
  actions?: ReactNode;
  className?: string;
  emptyMessage?: string;
}

interface DataTableColumnMeta {
  className?: string;
}

const dataTableFeatures = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { includesString: filterFn_includesString },
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
  columnMeta: {} as DataTableColumnMeta,
});

function getCellValue<TData extends object>(row: TData, key: string): unknown {
  return Reflect.get(row, key);
}

/**
 * Reusable data table backed by TanStack Table for sorting, filtering, and pagination.
 */
export function DataTable<TData extends object>({
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
}: DataTableProps<TData>) {
  const tableColumns = useMemo<ColumnDef<typeof dataTableFeatures, TData, unknown>[]>(
    () =>
      columns.map((column) => ({
        id: column.key,
        accessorFn: (row: TData) => getCellValue(row, column.key),
        header: column.label,
        enableSorting: column.sortable ?? false,
        enableGlobalFilter: column.key === searchKey,
        meta: { className: column.className },
        cell: ({ getValue, row }) => {
          const value = getValue();
          return column.render ? column.render(value, row.original) : String(value ?? "");
        },
      })),
    [columns, searchKey],
  );

  const table = useTable({
    features: dataTableFeatures,
    data,
    columns: tableColumns,
    initialState: { pagination: { pageIndex: 0, pageSize } },
    globalFilterFn: "includesString",
    getColumnCanGlobalFilter: (column) => column.id === searchKey,
    enableMultiSort: false,
    enableSortingRemoval: false,
    sortDescFirst: true,
  });

  const filter = String(table.state.globalFilter ?? "");
  const processedRows = table.getPrePaginatedRowModel().rows;
  const visibleRows = table.getRowModel().rows;
  const totalPages = table.getPageCount();
  const currentPage = table.state.pagination.pageIndex + 1;

  const handleFilterChange = (value: string) => {
    table.setGlobalFilter(value);
    table.setPageIndex(0);
  };

  return (
    <div
      className={`card bg-base-100 shadow-xl rounded-xl p-4 sm:p-8 border border-base-300 ${className}`}
    >
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4 sm:mb-6">
        <div className="flex flex-wrap items-center gap-2 sm:gap-4">
          <h2 className="text-lg sm:text-2xl font-semibold">{title}</h2>
          {actions}
        </div>

        <div className="flex items-center gap-2 sm:gap-4 w-full sm:w-auto">
          {searchable && (
            <div className="form-control flex-1 sm:flex-none">
              <input
                type="text"
                placeholder={searchPlaceholder}
                className="input input-bordered input-xs sm:input-sm w-full sm:w-64"
                value={filter}
                onChange={(event) => handleFilterChange(event.target.value)}
              />
            </div>
          )}
          <div className="text-xs sm:text-sm text-base-content/70 whitespace-nowrap">
            {filter ? `${processedRows.length} filtered` : `${data.length} total`}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto -mx-4 sm:mx-0 min-h-[300px]">
        {processedRows.length === 0 ? (
          <EmptyState
            title={filter ? "No results found" : emptyMessage}
            description={filter ? "Try adjusting your search criteria." : undefined}
            emoji={filter ? "magnifying-glass" : "empty"}
            size="sm"
          />
        ) : (
          <>
            <table className="table table-xs sm:table-compact table-zebra w-full border border-base-300 bg-base-100">
              <thead className="sticky top-0 bg-base-200">
                {table.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map((header) => {
                      const canSort = header.column.getCanSort();
                      const sortDirection = header.column.getIsSorted();
                      const meta = header.column.columnDef.meta;
                      return (
                        <th
                          key={header.id}
                          className={`${meta?.className || "text-center"} text-xs sm:text-sm px-2 sm:px-4 ${
                            canSort ? "cursor-pointer hover:bg-base-300" : ""
                          }`}
                          onClick={header.column.getToggleSortingHandler()}
                          aria-sort={
                            sortDirection === "asc"
                              ? "ascending"
                              : sortDirection === "desc"
                                ? "descending"
                                : undefined
                          }
                        >
                          <div className="flex items-center gap-1 justify-center">
                            <span className="truncate max-w-[80px] sm:max-w-none">
                              {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                            </span>
                            {canSort && sortDirection && (
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
                                aria-hidden="true"
                              >
                                <path d="M18 15l-6-6-6 6" />
                              </svg>
                            )}
                          </div>
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={row.id} className="transition-colors hover:bg-base-200/80">
                    {row.getAllCells().map((cell) => {
                      const meta = cell.column.columnDef.meta;
                      return (
                        <td
                          key={cell.id}
                          className={`${meta?.className || "text-center"} text-xs sm:text-sm px-2 sm:px-4`}
                        >
                          <table.FlexRender cell={cell} />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>

            {totalPages > 1 && (
              <div className="flex flex-col sm:flex-row justify-between items-center gap-2 mt-4 px-4 sm:px-0">
                <div className="text-xs sm:text-sm text-base-content/70">
                  {visibleRows.length} / {processedRows.length}
                </div>
                <div className="join">
                  <button
                    type="button"
                    className="join-item btn btn-xs sm:btn-sm"
                    onClick={() => table.previousPage()}
                    disabled={!table.getCanPreviousPage()}
                  >
                    Prev
                  </button>
                  <button
                    type="button"
                    className="join-item btn btn-xs sm:btn-sm btn-disabled"
                    disabled
                  >
                    {currentPage}/{totalPages}
                  </button>
                  <button
                    type="button"
                    className="join-item btn btn-xs sm:btn-sm"
                    onClick={() => table.nextPage()}
                    disabled={!table.getCanNextPage()}
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
