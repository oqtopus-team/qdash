import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  getFilteredRowModel,
} from "@tanstack/react-table";

function TableHeader({ table }) {
  return (
    <thead>
      {table.getHeaderGroups().map((headerGroup) => (
        <tr key={headerGroup.id}>
          {headerGroup.headers.map((header) => (
            <th key={header.id} colSpan={header.colSpan}>
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
  );
}

function TableBody({ table }) {
  return (
    <tbody>
      {table.getRowModel().rows.map((row) => {
        return (
          <tr key={row.id}>
            {row.getVisibleCells().map((cell) => {
              return (
                <td key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              );
            })}
          </tr>
        );
      })}
    </tbody>
  );
}

export function Table({ data, columns, filter }) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div className="overflow-x-auto card bg-base-200 shadow">
      <div className="flex justify-start items-center my-1">
        <input
          placeholder={`Filter by ${filter} ...`}
          value={(table.getColumn(filter)?.getFilterValue() as string) ?? ""}
          onChange={(e) =>
            table.getColumn(filter)?.setFilterValue(e.target.value)
          }
          className="input input-bordered w-56 bg-base-200"
        />
      </div>
      <table className="table">
        <TableHeader table={table} />
        <TableBody table={table} />
      </table>
    </div>
  );
}
