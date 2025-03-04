"use client";

import { useState } from "react";
import { useTheme } from "@/app/providers/theme-provider";
import { toast } from "react-toastify";
import yaml from "js-yaml";
import Editor from "@monaco-editor/react";
import { BsPlus } from "react-icons/bs";
import { useCreateMenu } from "@/client/menu/menu";
import type { CreateMenuRequest } from "@/schemas";

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

export function CreateFromTemplateModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
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
            onSuccess: () => {
              toast.success("Template item created successfully!");
              onSuccess();
              onClose();
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
            <h2 className="text-2xl font-bold">Create Menu from Template</h2>
            <p className="text-base-content/70 mt-1">
              Edit the template below to create a new menu
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
              value={templateText}
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
            onClick={handleSaveClick}
            disabled={!!validationError}
          >
            Create
          </button>
        </div>
      </div>
    </div>
  );
}
