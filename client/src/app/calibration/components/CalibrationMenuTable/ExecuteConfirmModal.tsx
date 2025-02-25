"use client";

import { useState } from "react";
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

  const handleYamlChange = (value) => {
    if (value !== undefined) {
      setYamlText(value);
      try {
        yaml.load(value); // Validate YAML format
        setValidationError("");
      } catch (error) {
        setValidationError("YAMLの形式が正しくありません: " + error.message);
      }
    }
  };

  const handleConfirmClick = () => {
    if (!validationError) {
      try {
        const updatedItem = yaml.load(yamlText) as Menu;
        onConfirm(updatedItem);
      } catch (error) {
        toast.error("YAMLのパースに失敗しました: " + error.message);
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
          theme="light"
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
description: ${data.description}
one_qubit_calib_plan:
${data.one_qubit_calib_plan
  .map((seq) => `  - ${JSON.stringify(seq)}`)
  .join("\n")}
two_qubit_calib_plan:
${data.two_qubit_calib_plan
  .map((seq) => `  - ${JSON.stringify(seq)}`)
  .join("\n")}
mode: ${data.mode}
notify_bool: ${data.notify_bool}
flow:
  - ${data.flow.join("\n  - ")}
tags:
  - ${(data.tags ?? []).join("\n  - ")}
exp_list:
  - ${(data.exp_list ?? []).join("\n  - ")}
  `;
}
