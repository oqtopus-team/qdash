"use client";

import "react18-json-view/src/style.css";
import { useEffect, useState } from "react";
import { FaRegSquarePlus } from "react-icons/fa6";
import { toast } from "react-toastify";

import { mapListMenuResponseToListMenu } from "../../model";
import { getColumns } from "./Columns";
import { NewItemModal } from "./NewItemModal";
import { TableEditModal } from "./TableEditModal";
import { NewItemModalFromTemplate } from "./NewItemModalFromTemplate";
import { ExecuteConfirmModal } from "./ExecuteConfirmModal";

import type { Menu } from "../../model";
import { useExecuteCalib } from "@/client/calibration/calibration";
import { useFetchExecutionLockStatus } from "@/client/execution/execution";
import { useListMenu, useDeleteMenu } from "@/client/menu/menu";
import { Table } from "@/app/components/Table";

// Initial selected item
const INITIAL_SELECTED_ITEM: Menu = {
  name: "open-service",
  description: "open-service",
  one_qubit_calib_plan: [[0], [0]],
  two_qubit_calib_plan: [
    [0, 1],
    [0, 2],
  ],
  mode: "mode",
  notify_bool: false,
  tags: ["tags"],
  flow: ["flow"],
};

export function CalibrationMenuTable() {
  const { data, isError, isLoading, refetch: refetchMenu } = useListMenu();
  const deleteMutation = useDeleteMenu();
  const executeCalibMutation = useExecuteCalib();
  const {
    data: lockStatus,
    isLoading: isLockStatusLoading,
    refetch: refetchLockStatus,
  } = useFetchExecutionLockStatus();
  const [lock, setLock] = useState<boolean>();
  const [tableData, setTableData] = useState<Menu[]>([]);
  const [selectedItem, setSelectedItem] = useState<Menu>(INITIAL_SELECTED_ITEM);
  const [showConfirmModal, setShowConfirmModal] = useState(false); // モーダル表示の状態

  useEffect(() => {
    if (data) {
      setTableData(mapListMenuResponseToListMenu(data.data));
    }
  }, [data]);

  useEffect(() => {
    if (lockStatus) {
      setLock(lockStatus.data.lock);
    }
  }, [lockStatus]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      refetchLockStatus();
    }, 5000); // 5秒ごとにロック状態を確認

    return () => clearInterval(intervalId); // クリーンアップ
  }, [refetchLockStatus]);

  const calibrationExecutedNotify = (flow_run_url: string) => {
    const localUrl = flow_run_url.replace(
      "http://172.22.0.5:4200",
      "http://localhost:4200"
    );
    toast(
      <div>
        <a
          href={localUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-500 underline"
        >
          Check detail from here! 🚀
        </a>
      </div>
    );
  };

  const handleExecuteCalib = (menu: Menu) => {
    setSelectedItem(menu);
    setShowConfirmModal(true); // 確認モーダルを表示
  };

  const confirmExecution = (updatedItem: Menu) => {
    executeCalibMutation.mutate(
      { data: updatedItem },
      {
        onSuccess: (response) => {
          calibrationExecutedNotify(response.data.flow_run_url);
          setShowConfirmModal(false); // モーダルを閉じる
        },
        onError: (error) => {
          console.error("Error executing calibration:", error);
          toast.error("Error executing calibration");
        },
      }
    );
  };

  const handleDeleteClick = (item: Menu) => {
    deleteMutation.mutate(
      { name: item.name },
      {
        onSuccess: async () => {
          const updatedData = await refetchMenu();
          if (updatedData.data) {
            setTableData(mapListMenuResponseToListMenu(updatedData.data.data));
          }
        },
        onError: (error) => {
          console.error("Error deleting menu:", error);
        },
      }
    );
  };

  const handleNewItem = () => {
    const newItemModal = document.getElementById(
      "newItem"
    ) as HTMLDialogElement | null;
    if (newItemModal) {
      newItemModal.showModal();
    }
  };

  const handleCreateTemplate = () => {
    const createTemplateModal = document.getElementById(
      "createTemplate"
    ) as HTMLDialogElement | null;
    if (createTemplateModal) {
      createTemplateModal.showModal();
    }
  };

  const handleEditClick = (item: Menu) => {
    setSelectedItem(item);
    const editModal = document.getElementById(
      "tableEdit"
    ) as HTMLDialogElement | null;
    if (editModal) {
      editModal.showModal();
    }
  };

  if (isLoading || isLockStatusLoading) {
    return <div>Loading...</div>;
  }
  if (isError) {
    return <div>Error</div>;
  }

  const columns = getColumns(
    handleEditClick,
    handleDeleteClick,
    handleExecuteCalib,
    lock ?? false // ロック状態を渡す
  );

  return (
    <div>
      <div className="flex justify-between">
        <h2 className="text-left text-2xl font-bold px-4 pb-4 py-4">
          Calibration Menu
        </h2>
        <div className="flex justify-end py-4">
          <div className="flex items-center">
            <button className="btn mx-4 bg-neutral" onClick={handleNewItem}>
              <FaRegSquarePlus className="text-neutral-content" />
              <div className="text-neutral-content">From File</div>
            </button>
            <button
              className="btn mx-4 bg-neutral"
              onClick={handleCreateTemplate}
            >
              <FaRegSquarePlus className="text-neutral-content" />
              <div className="text-neutral-content">From Template</div>
            </button>
          </div>
        </div>
      </div>
      <Table data={tableData} columns={columns} filter={"name"} />
      <TableEditModal
        selectedItem={selectedItem}
        setSelectedItem={setSelectedItem}
        setTableData={setTableData}
        refetchMenu={refetchMenu}
      />
      <NewItemModal setTableData={setTableData} refetchMenu={refetchMenu} />
      <NewItemModalFromTemplate
        setTableData={setTableData}
        refetchMenu={refetchMenu}
      />
      {/* 確認モーダルの表示 */}
      {showConfirmModal && (
        <ExecuteConfirmModal
          selectedItem={selectedItem}
          onConfirm={confirmExecution}
          onCancel={() => setShowConfirmModal(false)}
        />
      )}
    </div>
  );
}
