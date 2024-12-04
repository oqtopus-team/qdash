import { createColumnHelper } from "@tanstack/react-table";
import { RiDeleteBin6Line } from "react-icons/ri";

import type { CalibSchedule } from "../../model";

const columnHelper = createColumnHelper<CalibSchedule>();

export const getColumns = (
  handleDeleteClick: (item: CalibSchedule) => void,
) => [
  columnHelper.accessor("menu_name", {
    header: "Menu Name",
    cell: (info) => info.getValue(),
  }),
  columnHelper.accessor("description", {
    header: "Description",
    cell: (info) => info.getValue(),
  }),
  columnHelper.accessor("note", {
    header: "Note",
    cell: (info) => info.getValue(),
  }),
  columnHelper.accessor("timezone", {
    header: "Timezone",
    cell: (info) => info.getValue(),
  }),
  columnHelper.accessor("scheduled_time", {
    header: "Scheduled Time",
    cell: (info) => info.getValue(),
  }),
  columnHelper.display({
    id: "tableDelete",
    cell: (props) => (
      <div className="flex items-center">
        <button
          className="btn btn-sm btn-outline btn-error"
          onClick={() => handleDeleteClick(props.row.original)}
        >
          <RiDeleteBin6Line />
          Delete
        </button>
      </div>
    ),
  }),
];
