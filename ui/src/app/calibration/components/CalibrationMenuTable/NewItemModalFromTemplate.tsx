"use client";

import { useState } from "react";

import Editor from "@monaco-editor/react";
import yaml from "js-yaml";
import { toast } from "react-toastify";

import { mapListMenuResponseToListMenu } from "../../model";

import type { Menu } from "../../model";
import type { CreateMenuRequest } from "@/schemas";
import type { UseQueryResult } from "@tanstack/react-query";

import { useTheme } from "@/app/providers/theme-provider";
import { useCreateMenu } from "@/client/menu/menu";

// テンプレートの初期データ
const templateData = `
name: template
description: calibration menu template
qids:
  - ["Q1"]
  - ["Q2", "Q3"]
notify_bool: false
tasks:
  - task1
  - task2
tags:
  - calibration
  - template
`;

export function NewItemModalFromTemplate({
  setTableData,
  refetchMenu,
}: {
  setTableData: (data: Menu[]) => void;
  refetchMenu: () => Promise<UseQueryResult<any, any>>;
}) {
  const createMutation = useCreateMenu();
  const [templateText, setTemplateText] = useState(templateData);
  const [validationError, setValidationError] = useState("");
  const { theme } = useTheme();

  const handleYamlChange = (value: string | undefined) => {
    if (value !== undefined) {
      setTemplateText(value);
      try {
        yaml.load(value);
        setValidationError("");
      } catch (error) {
        setValidationError(
          "YAMLの形式が正しくありません: " +
            (error instanceof Error ? error.message : String(error)),
        );
      }
    }
  };

  const handleSaveClick = async () => {
    try {
      const formattedData = yaml.load(templateText) as CreateMenuRequest;

      if (formattedData && typeof formattedData === "object") {
        createMutation.mutate(
          { data: formattedData },
          {
            onSuccess: async () => {
              const updatedData = await refetchMenu();
              if (updatedData.data) {
                setTableData(
                  mapListMenuResponseToListMenu(updatedData.data.data),
                );
                toast.success("Template item created successfully!");
              }
            },
            onError: (error) => {
              console.error("Error creating template item:", error);
              toast.error("Error creating template item");
            },
          },
        );
      }
    } catch (error) {
      console.error("YAMLパースエラー:", error);
      toast.error("YAMLの形式が正しくありません");
    }
  };

  return (
    <dialog id="createTemplate" className="modal">
      <div className="modal-box">
        <h3 className="font-bold text-lg">Create Menu from Template</h3>
        <Editor
          height="600px"
          defaultLanguage="yaml"
          value={templateText}
          onChange={handleYamlChange}
          theme={theme === "dark" ? "vs-dark" : "light"}
          options={{
            fontSize: 16,
            lineNumbers: "off",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
          }}
        />
        {validationError && (
          <div className="text-error mt-2">{validationError}</div>
        )}
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
