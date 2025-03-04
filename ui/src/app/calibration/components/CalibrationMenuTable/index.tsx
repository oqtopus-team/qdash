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
import { MenuPreviewModal } from "./MenuPreviewModal";
import { EditConfirmModal } from "./EditConfirmModal";

import type { Menu } from "../../model";
import type { GetMenuResponse } from "@/schemas";
import { useListMenu, useDeleteMenu } from "@/client/menu/menu";
import { useExecuteCalib } from "@/client/calibration/calibration";
import { useAuth } from "@/app/contexts/AuthContext";
import { Table } from "@/app/components/Table";

// Initial selected item
const INITIAL_SELECTED_ITEM: Menu = {
  name: "default-menu",
  username: "default-user",
  description: "Default calibration menu",
  qids: [["Q1"], ["Q2", "Q3"]],
  notify_bool: false,
  tags: ["calibration"],
};

export function CalibrationMenuTable() {
  const { data, isError, isLoading, refetch: refetchMenu } = useListMenu();
  const deleteMutation = useDeleteMenu();
  const executeCalibMutation = useExecuteCalib();
  const { user } = useAuth();
  const [tableData, setTableData] = useState<Menu[]>([]);
  const [selectedItem, setSelectedItem] = useState<Menu>(INITIAL_SELECTED_ITEM);
  const [selectedMenuForPreview, setSelectedMenuForPreview] =
    useState<GetMenuResponse | null>(null);
  const [showExecuteConfirmModal, setShowExecuteConfirmModal] = useState(false);
  const [showMenuPreview, setShowMenuPreview] = useState(false);

  useEffect(() => {
    if (data) {
      setTableData(mapListMenuResponseToListMenu(data.data));
    }
  }, [data]);

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

  const handleEditClick = async (item: Menu) => {
    setSelectedItem(item);
    // メニューの詳細情報を取得
    const menuData = await refetchMenu();
    if (menuData.data) {
      const menuWithDetails = menuData.data.data.menus.find(
        (menu: GetMenuResponse) => menu.name === item.name
      );
      if (menuWithDetails) {
        setSelectedMenuForPreview(menuWithDetails);
        setShowMenuPreview(true);
        const menuPreviewModal = document.getElementById(
          "menuPreview"
        ) as HTMLDialogElement | null;
        if (menuPreviewModal) {
          menuPreviewModal.showModal();
        }
      }
    }
  };

  if (isLoading) {
    return <div>Loading...</div>;
  }
  if (isError) {
    return <div>Error</div>;
  }

  const handleExecuteCalib = (item: Menu) => {
    setSelectedItem(item);
    setShowExecuteConfirmModal(true);
  };

  const columns = getColumns(
    handleEditClick,
    handleDeleteClick,
    handleExecuteCalib,
    false // Temporarily disable lock
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
      {showExecuteConfirmModal && (
        <ExecuteConfirmModal
          selectedItem={selectedItem}
          onConfirm={(updatedItem) => {
            executeCalibMutation.mutate(
              {
                data: {
                  ...updatedItem,
                  username: user?.username ?? "default-user",
                },
              },
              {
                onSuccess: () => {
                  toast.success("Calibration execution started!");
                  setShowExecuteConfirmModal(false);
                },
                onError: (error) => {
                  console.error("Error executing calibration:", error);
                  toast.error("Error executing calibration");
                },
              }
            );
          }}
          onCancel={() => setShowExecuteConfirmModal(false)}
        />
      )}
      {showMenuPreview && selectedMenuForPreview && (
        <MenuPreviewModal
          selectedItem={selectedMenuForPreview}
          onClose={() => {
            setShowMenuPreview(false);
            setSelectedMenuForPreview(null);
          }}
        />
      )}
    </div>
  );
}
