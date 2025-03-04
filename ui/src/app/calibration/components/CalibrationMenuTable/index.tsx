"use client";

import "react18-json-view/src/style.css";
import { useEffect, useState } from "react";
import { toast } from "react-toastify";

import { mapListMenuResponseToListMenu } from "../../model";
import { getColumns } from "./Columns";
import { ExecuteConfirmModal } from "./ExecuteConfirmModal";
import { MenuPreviewModal } from "./MenuPreviewModal";

import type { Menu } from "../../model";
import type { GetMenuResponse } from "@/schemas";
import { useListMenu } from "@/client/menu/menu";
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
    return (
      <div className="flex items-center justify-center h-64">
        <div className="loading loading-spinner loading-lg text-primary"></div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="alert alert-error">
        <span>Failed to load calibration menus</span>
      </div>
    );
  }

  const handleExecuteCalib = (item: Menu) => {
    setSelectedItem(item);
    setShowExecuteConfirmModal(true);
  };

  const columns = getColumns(
    handleEditClick,
    () => {}, // Delete handler is no longer needed
    handleExecuteCalib,
    false // Temporarily disable lock
  );

  return (
    <div className="bg-base-100 rounded-box shadow-lg">
      <div className="border-b border-base-300 px-6 py-4">
        <h2 className="text-2xl font-bold">Calibration Menu</h2>
      </div>
      <div className="p-6">
        <Table data={tableData} columns={columns} filter={"name"} />
      </div>
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
