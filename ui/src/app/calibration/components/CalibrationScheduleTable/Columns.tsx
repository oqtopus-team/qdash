"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { RiDeleteBin6Line } from "react-icons/ri";
import type { ScheduleCalibResponse } from "@/schemas";

const columnHelper = createColumnHelper<ScheduleCalibResponse>();

export const getColumns = (
  handleDeleteClick: (item: ScheduleCalibResponse) => void
) => [
  columnHelper.accessor("menu_name", {
    header: "Menu Name",
    cell: (info) => <div className="font-medium">{info.getValue()}</div>,
  }),
  columnHelper.accessor("description", {
    header: "Description",
    cell: (info) => (
      <div className="text-base-content/70">{info.getValue()}</div>
    ),
  }),
  columnHelper.accessor("note", {
    header: "Note",
    cell: (info) => (
      <div className="text-base-content/70">{info.getValue()}</div>
    ),
  }),
  columnHelper.accessor("timezone", {
    header: "Timezone",
    cell: (info) => (
      <div className="badge badge-outline">{info.getValue()}</div>
    ),
  }),
  columnHelper.accessor("scheduled_time", {
    header: "Scheduled Time",
    cell: (info) => {
      const date = new Date(info.getValue());
      return (
        <div className="font-mono text-sm">
          {date.toLocaleString("ja-JP", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          })}
        </div>
      );
    },
  }),
  columnHelper.display({
    id: "actions",
    header: "Actions",
    cell: (props) => (
      <div className="flex items-center">
        <button
          className="btn btn-ghost btn-sm text-error hover:bg-error/10"
          onClick={() => handleDeleteClick(props.row.original)}
        >
          <RiDeleteBin6Line className="text-lg" />
        </button>
      </div>
    ),
  }),
];
