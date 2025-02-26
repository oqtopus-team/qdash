"use client";

import { useState } from "react";
import { useTheme } from "@/app/hooks/useTheme";
import { toast } from "react-toastify";
import yaml from "js-yaml";
import Editor from "@monaco-editor/react";

import { mapListMenuResponseToListMenu } from "../../model";
import { useCreateMenu } from "@/client/menu/menu";
import type { Menu } from "../../model";
import type { UseQueryResult } from "@tanstack/react-query";
import type { CreateMenuRequest } from "@/schemas";

// テンプレートの初期データ
const templateData = `
name: template
description: full calibration for mux9
one_qubit_calib_plan:
  - [0, 1, 2]
  - [4, 5, 6]
  - [7, 8, 9]
two_qubit_calib_plan:
  - [[0, 1], [0, 2], [3, 4]]
  - [[5, 6], [7, 8]]
mode: calib
notify_bool: false
flow:
  - one-qubit-calibration-flow
  - one-qubit-jazz-flow
  - lock-devices-flow
  - two-qubit-calibration-flow
tags:
  - tag1
  - tag2
exp_list:
  - exp1
  - exp2
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
            (error instanceof Error ? error.message : String(error))
        );
      }
    }
  };

  const handleSaveClick = async () => {
    try {
      const parsedData = yaml.load(templateText) as CreateMenuRequest;

      if (parsedData && typeof parsedData === "object") {
        // Convert two_qubit_calib_plan to the correct format
        const formattedData: CreateMenuRequest = {
          ...parsedData,
          two_qubit_calib_plan: parsedData.two_qubit_calib_plan.map((pairs) =>
            pairs.map((pair) => [pair[0], pair[1]] as [number, number])
          ),
        };

        createMutation.mutate(
          { data: formattedData },
          {
            onSuccess: async () => {
              const updatedData = await refetchMenu();
              if (updatedData.data) {
                setTableData(
                  mapListMenuResponseToListMenu(updatedData.data.data)
                );
                toast.success("Template item created successfully!");
              }
            },
            onError: (error) => {
              console.error("Error creating template item:", error);
              toast.error("Error creating template item");
            },
          }
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
