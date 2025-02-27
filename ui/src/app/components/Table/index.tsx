"use client";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useState } from "react";

interface TableProps<T> {
  data: T[];
  columns: ColumnDef<T, any>[];
  filter?: string;
}

export function Table<T>({ data, columns, filter }: TableProps<T>) {
  const [filtering, setFiltering] = useState("");

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    state: {
      globalFilter: filtering,
    },
    onGlobalFilterChange: setFiltering,
  });

  return (
    <div className="px-4">
      {filter && (
        <div className="flex justify-end py-4">
          <input
            type="text"
            value={filtering}
            onChange={(e) => setFiltering(e.target.value)}
            placeholder={`Search by ${filter}...`}
            className="input input-bordered w-full max-w-xs"
          />
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="table">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex justify-center py-4">
        <div className="join">
          <button
            className="join-item btn"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            «
          </button>
          <button className="join-item btn">
            Page {table.getState().pagination.pageIndex + 1} of{" "}
            {table.getPageCount()}
          </button>
          <button
            className="join-item btn"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            »
          </button>
        </div>
      </div>
    </div>
  );
}
