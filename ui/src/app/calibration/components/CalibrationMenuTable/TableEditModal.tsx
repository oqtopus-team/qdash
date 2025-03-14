"use client";

import "react18-json-view/src/style.css";
import { toast } from "react-toastify";
import yaml from "js-yaml";
import { useEffect, useState } from "react";
import { useTheme } from "@/app/providers/theme-provider";
import Editor from "@monaco-editor/react";

import { mapListMenuResponseToListMenu } from "../../model";
import { useUpdateMenu } from "@/client/menu/menu";

import type { Menu } from "../../model";
import type { UseQueryResult } from "@tanstack/react-query";
import type { UpdateMenuRequest } from "@/schemas";

interface YamlData {
  name: string;
  description: string;
  qids: string[][];
  notify_bool: boolean;
  tasks?: string[];
  tags?: string[];
}

// YAML 形式でデータを生成する関数
function generateYamlWithCustomArrayFormat(data: Menu): string {
  return `
name: ${data.name}
description: ${data.description}
qids:
${data.qids.map((seq) => `  - ${JSON.stringify(seq)}`).join("\n")}
notify_bool: ${data.notify_bool}
${
  data.tasks && data.tasks.length > 0
    ? `tasks:\n  - ${data.tasks.join("\n  - ")}`
    : ""
}
${
  data.tags && data.tags.length > 0
    ? `tags:\n  - ${data.tags.join("\n  - ")}`
    : ""
}
  `;
}

export function TableEditModal({
  selectedItem,
  setSelectedItem,
  setTableData,
  refetchMenu,
}: {
  selectedItem: Menu;
  setSelectedItem: (selectedItem: Menu) => void;
  setTableData: (tableData: Menu[]) => void;
  refetchMenu: () => Promise<UseQueryResult<any, any>>;
}) {
  const [yamlText, setYamlText] = useState(
    generateYamlWithCustomArrayFormat(selectedItem),
  );
  const [validationError, setValidationError] = useState("");
  const scheduleSettingChangedNotify = () => toast("schedule setting changed!");
  const mutation = useUpdateMenu();
  const { theme } = useTheme();

  useEffect(() => {
    setYamlText(generateYamlWithCustomArrayFormat(selectedItem));
  }, [selectedItem]);

  const handleYamlChange = (value: string | undefined) => {
    if (value !== undefined) {
      setYamlText(value);
      try {
        yaml.load(value);
        setValidationError("");
      } catch (error) {
        setValidationError(`Validation Error: ${error}`);
      }
    }
  };

  const handleSaveClick = async () => {
    try {
      const updatedItem = yaml.load(yamlText) as YamlData;

      const formattedItem: UpdateMenuRequest = {
        name: updatedItem.name,
        username: selectedItem.username, // Keep the original username
        description: updatedItem.description,
        qids: updatedItem.qids,
        notify_bool: updatedItem.notify_bool,
        tasks:
          updatedItem.tasks?.filter((item) => item !== null && item !== "") ??
          [],
        tags:
          updatedItem.tags?.filter((item) => item !== null && item !== "") ??
          [],
      };

      const menuItem: Menu = {
        name: updatedItem.name,
        username: selectedItem.username, // Keep the original username
        description: updatedItem.description,
        qids: updatedItem.qids,
        notify_bool: updatedItem.notify_bool,
        tasks:
          updatedItem.tasks?.filter((item) => item !== null && item !== "") ??
          [],
        tags:
          updatedItem.tags?.filter((item) => item !== null && item !== "") ??
          [],
      };

      setSelectedItem(menuItem);

      mutation.mutate(
        { name: selectedItem.name, data: formattedItem },
        {
          onSuccess: async () => {
            const updatedData = await refetchMenu();
            if (updatedData.data) {
              setTableData(
                mapListMenuResponseToListMenu(updatedData.data.data),
              );
              scheduleSettingChangedNotify();
            }
          },
          onError: (error) => {
            console.error("Error updating menu:", error);
          },
        },
      );
    } catch (error) {
      console.error("YAMLパースエラー:", error);
      toast.error("YAMLの形式が正しくありません");
    }
  };

  return (
    <dialog id="tableEdit" className="modal">
      <div className="modal-box w-full max-w-7xl">
        <h3 className="font-bold text-lg mb-4">{selectedItem.name}</h3>
        <div className="flex">
          <div className="w-full p-2">
            <Editor
              height="800px"
              defaultLanguage="yaml"
              value={yamlText}
              onChange={handleYamlChange}
              theme={theme === "dark" ? "vs-dark" : "light"}
              language="yaml"
              options={{
                folding: true,
                foldingHighlight: true,
                fontSize: 16,
                lineNumbers: "off",
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
              }}
            />
            {validationError && (
              <div className="text-error mt-2">{validationError}</div>
            )}
          </div>
        </div>
        <div className="modal-action">
          <form method="dialog">
            <button
              className="btn"
              onClick={handleSaveClick}
              disabled={!!validationError}
            >
              Save
            </button>
          </form>
          <form method="dialog">
            <button className="btn">Close</button>
          </form>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );
}
