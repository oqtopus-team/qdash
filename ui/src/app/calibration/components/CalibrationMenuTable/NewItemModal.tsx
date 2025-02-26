"use client";

import "react18-json-view/src/style.css";
import { useState } from "react";

import { toast } from "react-toastify";
import yaml from "js-yaml"; // YAML を解析するためのライブラリ

import { mapListMenuResponseToListMenu } from "../../model";

import type { Menu } from "../../model";
import type { UseQueryResult } from "@tanstack/react-query";

import { useCreateMenu } from "@/client/menu/menu";

export function NewItemModal({
  setTableData,
  refetchMenu,
}: {
  setTableData: (data: Menu[]) => void;
  refetchMenu: () => Promise<UseQueryResult<any, any>>;
}) {
  const createMutation = useCreateMenu();
  const [fileData, setFileData] = useState<any>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!event.target.files) {
      return;
    }
    const file = event.target.files[0];
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        if (!event.target) {
          return;
        }
        const fileContent = event.target.result as string;

        // YAML パースを追加し、JSON オブジェクトに変換
        const data = yaml.load(fileContent);
        setFileData(data);
      } catch (error) {
        console.error("Invalid YAML", error);
        toast.error("Invalid YAML file");
      }
    };
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    if (fileData) {
      createMutation.mutate(
        { data: fileData },
        {
          onSuccess: async (response) => {
            console.log("File data uploaded successfully", response);
            const updatedData = await refetchMenu();
            if (updatedData.data) {
              const menu = mapListMenuResponseToListMenu(updatedData.data.data);
              setTableData([...menu]);
              toast.success("File uploaded successfully");
            }
          },
          onError: (error) => {
            console.error("Error uploading file", error);
            toast.error("Error uploading file");
          },
        },
      );
    }
  };

  return (
    <>
      <dialog id="newItem" className="modal">
        <div className="modal-box">
          <h3 className="font-bold text-lg my-4">Upload YAML File</h3>
          <input
            type="file"
            className="file-input file-input-bordered file-input-secondary w-full max-w-xs"
            accept=".yaml, .yml"
            onChange={handleFileChange}
          />

          <div className="modal-action">
            <form method="dialog">
              <button className="btn" onClick={handleSubmit}>
                Submit
              </button>
            </form>
            <form method="dialog">
              <button className="btn">Close</button>
            </form>
          </div>
        </div>
      </dialog>
    </>
  );
}
