"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { FaTrash } from "react-icons/fa";
import { FaRegCirclePlay } from "react-icons/fa6";
import type { MenuModel } from "@/schemas";

const columnHelper = createColumnHelper<MenuModel>();

export const getColumns = (
  handleEditClick: (item: MenuModel) => void,
  handleDeleteClick: (item: MenuModel) => void,
  handleExecuteCalib: (item: MenuModel) => void,
  isLocked: boolean,
) => [
  columnHelper.accessor("name", {
    header: "Name",
    cell: (info) => (
      <button
        className="link link-hover font-medium text-primary hover:text-primary-focus flex items-center gap-1"
        onClick={() => handleEditClick(info.row.original)}
      >
        <span>{info.getValue()}</span>
        <span className="text-xs opacity-50">(click to edit)</span>
      </button>
    ),
  }),
  columnHelper.accessor("description", {
    header: "Description",
    cell: (info) => info.getValue(),
  }),
  columnHelper.accessor("qids", {
    header: "QIDs",
    cell: (info) => (
      <div className="max-w-xs overflow-hidden">
        <div className="text-sm text-base-content/70">
          {info
            .getValue()
            .map((qids: string[]) => qids.join(", "))
            .join(" | ")}
        </div>
      </div>
    ),
  }),
  columnHelper.accessor("tags", {
    header: "Tags",
    cell: (info) => (
      <div className="flex flex-wrap gap-1">
        {info.getValue()?.map((tag: string) => (
          <span
            key={tag}
            className="badge badge-sm badge-outline badge-primary"
          >
            {tag}
          </span>
        ))}
      </div>
    ),
  }),
  columnHelper.display({
    id: "tableEdit",
    header: "Actions",
    cell: (props) => (
      <div className="flex items-center gap-2">
        <button
          className="btn btn-sm btn-ghost text-error hover:bg-error/10"
          onClick={() => handleDeleteClick(props.row.original)}
        >
          <FaTrash className="text-lg" />
        </button>
        <button
          className={`btn btn-sm btn-ghost text-accent hover:bg-accent/10 ${
            isLocked ? "btn-disabled" : ""
          }`}
          onClick={() => handleExecuteCalib(props.row.original)}
          disabled={isLocked}
          title={isLocked ? "Calibration is locked" : "Execute calibration"}
        >
          <FaRegCirclePlay className="text-lg" />
        </button>
      </div>
    ),
  }),
];
