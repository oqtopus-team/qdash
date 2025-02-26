"use client";

import { toast } from "react-toastify";
import { createColumnHelper } from "@tanstack/react-table";
import { FaEdit } from "react-icons/fa";
import { RiDeleteBin6Line } from "react-icons/ri";
import { FiDownload } from "react-icons/fi";
import yaml from "js-yaml";
import type { Menu } from "../../model";
import { FaRegCirclePlay } from "react-icons/fa6";
const columnHelper = createColumnHelper<Menu>();

function generateYamlWithCustomArrayFormat(data) {
  return `
name: ${data.name}
description: ${data.description}
one_qubit_calib_plan:
${data.one_qubit_calib_plan
  .map((seq) => `  - ${JSON.stringify(seq)}`)
  .join("\n")}
two_qubit_calib_plan:
${data.two_qubit_calib_plan
  .map((seq) => `  - ${JSON.stringify(seq)}`)
  .join("\n")}
mode: ${data.mode}
notify_bool: ${data.notify_bool}
flow:
  - ${data.flow.join("\n  - ")}
tags:
  - ${(data.tags ?? []).join("\n  - ")}
exp_list:
  - ${(data.exp_list ?? []).join("\n  - ")}
  `;
}

// YAML ファイルをダウンロードする関数
const downloadYaml = (menu: Menu) => {
  const yamlDataCustom = generateYamlWithCustomArrayFormat(menu);
  const blob = new Blob([yamlDataCustom], { type: "application/x-yaml" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = `${menu.name}.yaml`; // ファイル名はメニュー名
  a.click();
  toast.success("YAML file downloaded successfully");
  // リソースを解放
  URL.revokeObjectURL(url);
};

// 各種アクションハンドラを受け取る形でカラム定義関数を作成
export const getColumns = (
  handleEditClick: (item: Menu) => void,
  handleDeleteClick: (item: Menu) => void,
  handleExecuteCalib: (item: Menu) => void,
  isLocked: boolean,
) => [
  columnHelper.accessor("name", {
    header: "Name",
    cell: (info) => info.getValue(),
  }),
  columnHelper.accessor("description", {
    header: "Description",
    cell: (info) => info.getValue(),
  }),
  columnHelper.accessor("one_qubit_calib_plan", {
    header: "One Qubit Calib Plan",
    cell: (info) => JSON.stringify(info.getValue()), // YAML形式にしたい場合は別途変換
  }),
  columnHelper.accessor("two_qubit_calib_plan", {
    header: "Two Qubit Calib Plan",
    cell: (info) => JSON.stringify(info.getValue()), // YAML形式にしたい場合は別途変換
  }),
  columnHelper.accessor("mode", {
    header: "Mode",
    cell: (info) => info.getValue(),
  }),
  columnHelper.accessor("tags", {
    header: "Tags",
    cell: (info) => JSON.stringify(info.getValue()), // YAML形式にしたい場合は別途変換
  }),
  columnHelper.display({
    id: "tableEdit",
    header: "Actions",
    cell: (props) => (
      <div className="flex items-center space-x-2">
        <div className="tooltip" data-tip={"Edit calibration menu"}>
          <button
            className="btn btn-sm btn-outline btn-secondary whitespace-nowrap text-ellipsis"
            onClick={() => handleEditClick(props.row.original)}
          >
            <FaEdit className="mr-1" />
          </button>
        </div>
        <div className="tooltip" data-tip={"Delete calibration menu"}>
          <button
            className="btn btn-sm btn-outline btn-error whitespace-nowrap text-ellipsis"
            onClick={() => handleDeleteClick(props.row.original)}
          >
            <RiDeleteBin6Line className="mr-1" />
          </button>
        </div>
        <div
          className="tooltip"
          data-tip={
            isLocked ? "Calibration is locked 🚫 " : "Execute calibration"
          }
        >
          <button
            className={`btn btn-sm btn-outline btn-neutral whitespace-nowrap text-ellipsis ${
              isLocked ? "btn-disabled" : ""
            }`}
            onClick={() => handleExecuteCalib(props.row.original)}
            tabIndex={isLocked ? -1 : 0}
            role={isLocked ? "button" : undefined}
            aria-disabled={isLocked ? "true" : "false"}
          >
            <FaRegCirclePlay />
          </button>
        </div>
        <div className="tooltip" data-tip={"Download YAML"}>
          <button
            className="btn btn-sm btn-outline btn-primary whitespace-nowrap text-ellipsis"
            onClick={() => downloadYaml(props.row.original)}
          >
            <FiDownload className="mr-1" />
          </button>
        </div>
      </div>
    ),
  }),
];
