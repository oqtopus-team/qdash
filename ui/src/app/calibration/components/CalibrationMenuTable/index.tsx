"use client";

import "react18-json-view/src/style.css";
import { useEffect, useState } from "react";
import { toast } from "react-toastify";

import { getColumns } from "./Columns";
import { ExecuteConfirmModal } from "./ExecuteConfirmModal";
import { MenuPreviewModal } from "./MenuPreviewModal";
import { DeleteConfirmModal } from "./DeleteConfirmModal";

import type { MenuModel, GetMenuResponse } from "@/schemas";
import { useListMenu, useDeleteMenu } from "@/client/menu/menu";
import { useExecuteCalib } from "@/client/calibration/calibration";
import { useAuth } from "@/app/contexts/AuthContext";
import { Table } from "@/app/components/Table";

// Initial selected item
const INITIAL_SELECTED_ITEM: MenuModel = {
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
  const deleteMutation = useDeleteMenu();
  const { user } = useAuth();
  const [tableData, setTableData] = useState<MenuModel[]>([]);
  const [selectedItem, setSelectedItem] = useState<MenuModel>(
    INITIAL_SELECTED_ITEM,
  );
  const [selectedMenuForPreview, setSelectedMenuForPreview] =
    useState<GetMenuResponse | null>(null);
  const [showExecuteConfirmModal, setShowExecuteConfirmModal] = useState(false);
  const [showDeleteConfirmModal, setShowDeleteConfirmModal] = useState(false);
  const [showMenuPreview, setShowMenuPreview] = useState(false);

  useEffect(() => {
    if (data?.data?.menus) {
      setTableData(data.data.menus);
    }
  }, [data]);

  const handleEditClick = async (item: MenuModel) => {
    setShowMenuPreview(true);
    const menuData = await refetchMenu();
    if (menuData.data) {
      const menuWithDetails = menuData.data.data.menus.find(
        (menu: GetMenuResponse) => menu.name === item.name,
      );
      if (menuWithDetails) {
        setSelectedMenuForPreview(menuWithDetails);
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

  const handleExecuteCalib = (item: MenuModel) => {
    setSelectedItem(item);
    setShowExecuteConfirmModal(true);
  };

  const handleDeleteClick = (item: MenuModel) => {
    setSelectedItem(item);
    setShowDeleteConfirmModal(true);
  };

  const columns = getColumns(
    handleEditClick,
    handleDeleteClick,
    handleExecuteCalib,
    false, // isLocked
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
              },
            );
          }}
          onCancel={() => setShowExecuteConfirmModal(false)}
        />
      )}
      {showDeleteConfirmModal && (
        <DeleteConfirmModal
          selectedItem={selectedItem}
          onConfirm={() => {
            deleteMutation.mutate(
              { name: selectedItem.name },
              {
                onSuccess: () => {
                  toast.success("Menu deleted successfully");
                  setShowDeleteConfirmModal(false);
                  refetchMenu(); // 一覧を更新
                },
                onError: (error) => {
                  console.error("Error deleting menu:", error);
                  toast.error("Error deleting menu");
                },
              },
            );
          }}
          onCancel={() => setShowDeleteConfirmModal(false)}
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
