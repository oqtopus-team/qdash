"use client";

import { useState } from "react";
import { useTheme } from "@/app/hooks/useTheme";
import Editor from "@monaco-editor/react";
import { toast } from "react-toastify";
import yaml from "js-yaml";

import type { Menu } from "../../model";

export function ExecuteConfirmModal({
  selectedItem,
  onConfirm,
  onCancel,
}: {
  selectedItem: Menu;
  onConfirm: (updatedItem: Menu) => void;
  onCancel: () => void;
}) {
  const [yamlText, setYamlText] = useState(
    generateYamlWithCustomArrayFormat(selectedItem),
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
        const updatedItem = yaml.load(yamlText) as Menu;
        onConfirm(updatedItem);
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
    <dialog open className="modal">
      <div className="modal-box">
        <h3 className="font-bold text-lg">Confirm Execution</h3>
        <p>
          Are you sure you want to execute the calibration with the following
          settings?
        </p>
        <Editor
          height="600px"
          defaultLanguage="yaml"
          value={yamlText}
          onChange={handleYamlChange}
          theme={theme === "dark" ? "vs-dark" : "light"}
          options={{
            fontSize: 16,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            lineNumbers: "off",
          }}
        />
        {validationError && (
          <div style={{ color: "red", marginTop: "8px" }}>
            {validationError}
          </div>
        )}
        <div className="modal-action">
          <button
            className="btn"
            onClick={handleConfirmClick}
            disabled={!!validationError}
          >
            Confirm
          </button>
          <button className="btn" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onCancel}>close</button>
      </form>
    </dialog>
  );
}

// YAML 形式でデータを生成する関数
function generateYamlWithCustomArrayFormat(data: Menu) {
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
