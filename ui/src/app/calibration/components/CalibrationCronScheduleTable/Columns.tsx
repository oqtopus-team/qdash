"use client";

import { createColumnHelper } from "@tanstack/react-table";
import type { ScheduleCronCalibResponse } from "@/schemas";

const columnHelper = createColumnHelper<ScheduleCronCalibResponse>();

export const getColumns = (
  handleToggle: (item: ScheduleCronCalibResponse, active: boolean) => void,
) => [
  columnHelper.accessor("scheduler_name", {
    header: "Scheduler Name",
    cell: (info) => <div className="font-medium">{info.getValue()}</div>,
  }),
  columnHelper.accessor("menu_name", {
    header: "Menu Name",
    cell: (info) => <div className="font-medium">{info.getValue()}</div>,
  }),
  columnHelper.accessor("cron", {
    header: "Cron Expression",
    cell: (info) => <div className="font-mono text-sm">{info.getValue()}</div>,
  }),
  columnHelper.accessor("active", {
    header: "Status",
    cell: (info) => (
      <div
        className={`badge ${info.getValue() ? "badge-success" : "badge-error"}`}
      >
        {info.getValue() ? "Active" : "Inactive"}
      </div>
    ),
  }),
  columnHelper.display({
    id: "actions",
    header: "Actions",
    cell: (props) => (
      <div className="flex items-center">
        <input
          type="checkbox"
          className="toggle toggle-primary"
          checked={props.row.original.active}
          onChange={(e) => handleToggle(props.row.original, e.target.checked)}
        />
      </div>
    ),
  }),
];
