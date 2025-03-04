"use client";

import { useState } from "react";
import { useTheme } from "@/app/providers/theme-provider";
import Editor from "@monaco-editor/react";
import { toast } from "react-toastify";
import yaml from "js-yaml";
import { GetMenuResponse } from "@/schemas";
import { useExecuteCalib } from "@/client/calibration/calibration";
import { useAuth } from "@/app/contexts/AuthContext";
import { BsPlus } from "react-icons/bs";

export function ExecuteConfirmModal({
  selectedMenu,
  onClose,
}: {
  selectedMenu: GetMenuResponse;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const executeCalibMutation = useExecuteCalib();
  const [yamlText, setYamlText] = useState(
    generateYamlWithCustomArrayFormat(selectedMenu),
  );
  const [validationError, setValidationError] = useState("");
  const { theme } = useTheme();

  const handleYamlChange = (value: string | undefined) => {
    if (value !== undefined) {
      setYamlText(value);
      try {
        yaml.load(value); // Validate YAML format
        setValidationError("");
      } catch (error) {
        setValidationError(
          "YAMLの形式が正しくありません: " +
            (error instanceof Error ? error.message : String(error)),
        );
      }
    }
  };

  const handleConfirmClick = () => {
    if (!validationError) {
      try {
        const updatedMenu = yaml.load(yamlText) as GetMenuResponse;
        executeCalibMutation.mutate(
          {
            data: {
              ...updatedMenu,
              username: user?.username ?? "default-user",
            },
          },
          {
            onSuccess: () => {
              toast.success("Calibration execution started!");
              onClose();
            },
            onError: (error) => {
              console.error("Error executing calibration:", error);
              toast.error("Error executing calibration");
            },
          },
        );
      } catch (error) {
        toast.error(
          "YAMLのパースに失敗しました: " +
            (error instanceof Error ? error.message : String(error)),
        );
      }
    } else {
      toast.error("YAMLの形式が正しくありません");
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-base-100 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
          <div>
            <h2 className="text-2xl font-bold">Execute Calibration</h2>
            <p className="text-base-content/70 mt-1">
              Review and confirm the calibration settings
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
          >
            <BsPlus className="text-xl rotate-45" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-6">
          <div className="h-[500px] rounded-lg overflow-hidden bg-base-300/30 shadow-inner">
            <Editor
              defaultLanguage="yaml"
              value={yamlText}
              onChange={handleYamlChange}
              theme={theme === "dark" ? "vs-dark" : "light"}
              options={{
                fontSize: 14,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                lineNumbers: "off",
                automaticLayout: true,
              }}
            />
          </div>
          {validationError && (
            <div className="mt-4 text-error text-sm">{validationError}</div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleConfirmClick}
            disabled={!!validationError}
          >
            Execute
          </button>
        </div>
      </div>
    </div>
  );
}

// YAML 形式でデータを生成する関数
function generateYamlWithCustomArrayFormat(data: GetMenuResponse) {
  return `
name: ${data.name}
username: ${data.username}
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
