import { createColumnHelper } from "@tanstack/react-table";
import { IoImageOutline } from "react-icons/io5";
import { MdHistory } from "react-icons/md";
import { TbListDetails } from "react-icons/tb";

import type { OneQubitCalibSummary } from "@/schemas";

const columnHelper = createColumnHelper<OneQubitCalibSummary>();

export const getColumns = (
  handleDetailClick: (item: OneQubitCalibSummary) => void,
  handleFigureClick: (item: OneQubitCalibSummary) => void,
  handleHistoryClick: (item: OneQubitCalibSummary) => void
) => [
  columnHelper.accessor("label", {
    header: "Qubit",
    cell: (info) => info.getValue(),
  }),
  columnHelper.display({
    id: "tableDetail",
    cell: (props) => (
      <div className="flex items-center">
        <button
          className="btn btn-sm btn-outline btn-secondary"
          onClick={() => handleDetailClick(props.row.original)}
        >
          <TbListDetails />
          Detail
        </button>
      </div>
    ),
  }),
  columnHelper.display({
    id: "tableHistory",
    cell: (props) => (
      <div className="flex items-center">
        <button
          className="btn btn-sm btn-outline btn-neutral"
          onClick={() => handleHistoryClick(props.row.original)}
        >
          <MdHistory />
          History
        </button>
      </div>
    ),
  }),
  columnHelper.display({
    id: "execute",
    cell: (props) => (
      <div className="flex items-center">
        <button
          className="btn btn-sm  btn-outline btn-accent"
          onClick={() => handleFigureClick(props.row.original)}
        >
          <IoImageOutline />
          Figure
        </button>
      </div>
    ),
  }),
];
