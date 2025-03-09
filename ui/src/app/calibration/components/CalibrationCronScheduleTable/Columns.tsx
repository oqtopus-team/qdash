"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { FaEdit } from "react-icons/fa";
import type { MenuModel, ScheduleCronCalibResponse } from "@/schemas";

const columnHelper = createColumnHelper<ScheduleCronCalibResponse>();

export const getColumns = (
  handleToggle: (item: ScheduleCronCalibResponse, active: boolean) => void,
  handleEdit: (item: ScheduleCronCalibResponse) => void,
  handleMenuClick: (menuName: string, menu: MenuModel) => void,
  menus: MenuModel[],
) => [
  columnHelper.accessor("scheduler_name", {
    header: "Scheduler Name",
    cell: (info) => <div className="font-medium">{info.getValue()}</div>,
  }),
  columnHelper.accessor("menu_name", {
    header: "Menu Name",
    cell: (info) => {
      const menuName = info.getValue();
      const menu = menus.find((m) => m.name === menuName);
      return (
        <button
          className="link link-hover font-medium text-primary hover:text-primary-focus flex items-center gap-1"
          onClick={() => menu && handleMenuClick(menuName, menu)}
        >
          <span>{menuName}</span>
          <span className="text-xs opacity-50">(click to edit)</span>
        </button>
      );
    },
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
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          className="toggle toggle-primary"
          checked={props.row.original.active}
          onChange={(e) => handleToggle(props.row.original, e.target.checked)}
        />
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => handleEdit(props.row.original)}
        >
          <FaEdit className="text-lg" />
        </button>
      </div>
    ),
  }),
];
