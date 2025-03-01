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

import type { Menu } from "../../model";
import { useListMenu, useDeleteMenu } from "@/client/menu/menu";
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
  const [tableData, setTableData] = useState<Menu[]>([]);
  const [selectedItem, setSelectedItem] = useState<Menu>(INITIAL_SELECTED_ITEM);

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

  const handleEditClick = (item: Menu) => {
    setSelectedItem(item);
    const editModal = document.getElementById(
      "tableEdit"
    ) as HTMLDialogElement | null;
    if (editModal) {
      editModal.showModal();
    }
  };

  if (isLoading) {
    return <div>Loading...</div>;
  }
  if (isError) {
    return <div>Error</div>;
  }

  const columns = getColumns(
    handleEditClick,
    handleDeleteClick,
    () => {}, // Temporarily disable execution
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
    </div>
  );
}
