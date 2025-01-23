import "react18-json-view/src/style.css";
import { toast } from "react-toastify";
import yaml from "js-yaml";
import { useEffect, useState } from "react";
import Editor from "@monaco-editor/react";

import { mapListMenuResponseToListMenu } from "../../model";
import { useUpdateMenu } from "@/client/menu/menu";

import type { Menu } from "../../model";
import type { UseQueryResult } from "@tanstack/react-query";

// YAML 形式でデータを生成する関数
function generateYamlWithCustomArrayFormat(data) {
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

const calib_list = ["Example1", "Example2", "Example3", "Example4"];

const presets = {
  default: [
    "CheckStatus",
    "LinkUp",
    "Configure",
    "DumpBox",
    "CheckNoise",
    "CheckQubitFrequency",
    "CheckReadoutFrequency",
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CreatePIPulse",
    "CheckPIPulse",
    "CheckT1",
    "CheckT2",
    "CheckEffectiveQubitFrequency",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "ReadoutClassification",
    "RandomizedBenchmarking",
    "InterleavedRandomizedBenchmarking",
    "CheckCrossResonance",
    "OptimizeZX90",
    "CreateZX90",
    "CreateFineZX90",
  ],
  preset1: ["Example1", "Example2", "Example3"],
  preset2: ["Example1", "Example2", "Example3", "Example4"],
  custom: [],
};
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
    generateYamlWithCustomArrayFormat(selectedItem)
  );
  const [validationError, setValidationError] = useState("");
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null); // 現在のプリセット
  const scheduleSettingChangedNotify = () => toast("schedule setting changed!");
  const mutation = useUpdateMenu();

  useEffect(() => {
    setYamlText(generateYamlWithCustomArrayFormat(selectedItem));
  }, [selectedItem]);

  const handleYamlChange = (value) => {
    if (value !== undefined) {
      setYamlText(value);
      try {
        yaml.load(value);
        setValidationError("");
      } catch (error) {
        setValidationError("Validation Error: " + error);
      }
    }
  };

  const handlePresetClick = (presetKey: keyof typeof presets) => {
    try {
      const updatedYaml = yaml.load(yamlText);
      if (updatedYaml && typeof updatedYaml === "object") {
        updatedYaml.exp_list = presets[presetKey]; // プリセットに置き換え
        updatedYaml.mode = presetKey; // mode をプリセット名に設定
        setYamlText(generateYamlWithCustomArrayFormat(updatedYaml)); // エディタの内容を更新
        setValidationError(""); // バリデーションエラーをクリア
        setSelectedPreset(presetKey); // 選択中のプリセットを設定
      }
    } catch (error) {
      console.error("YAMLパースエラー:", error);
      toast.error("プリセットの適用に失敗しました");
    }
  };

  const handleListItemClick = (item: string) => {
    try {
      const updatedYaml = yaml.load(yamlText);
      if (updatedYaml && typeof updatedYaml === "object") {
        // exp_list が存在しない場合は初期化
        if (!updatedYaml.exp_list) {
          updatedYaml.exp_list = [];
        }

        updatedYaml.exp_list.push(item); // YAML文字列を更新
        setYamlText(generateYamlWithCustomArrayFormat(updatedYaml)); // エディタの内容を更新
        setValidationError(""); // バリデーションエラーをクリア
        setSelectedPreset(null); // プリセット選択を解除
      }
    } catch (error) {
      console.error("YAMLパースエラー:", error);
      toast.error("エディタ内容の更新に失敗しました");
    }
  };
  const handleSaveClick = async () => {
    try {
      const updatedItem = yaml.load(yamlText);

      // mode が custom ではない場合のバリデーション
      if (updatedItem.mode !== "custom") {
        const allPresetItems = Object.values(presets).flat(); // 全プリセットの項目を統合
        const invalidItems = updatedItem.exp_list?.filter(
          (item) => !allPresetItems.includes(item)
        );

        if (invalidItems?.length > 0) {
          setValidationError(
            `exp_list に無効な項目が含まれています: ${invalidItems.join(", ")}`
          );
          return;
        }
      }

      if (updatedItem && typeof updatedItem === "object") {
        const formattedItem: Menu = {
          name: updatedItem.name,
          description: updatedItem.description,
          one_qubit_calib_plan: updatedItem.one_qubit_calib_plan,
          two_qubit_calib_plan: updatedItem.two_qubit_calib_plan,
          mode: updatedItem.mode,
          notify_bool: updatedItem.notify_bool,
          flow: updatedItem.flow,
          tags:
            updatedItem.tags?.filter((item: string | null) => item !== null) ??
            [],
          exp_list:
            updatedItem.exp_list?.filter(
              (item: string | null) => item !== null
            ) ?? [],
        };

        setSelectedItem(formattedItem);

        mutation.mutate(
          { name: selectedItem.name, data: formattedItem },
          {
            onSuccess: async () => {
              const updatedData = await refetchMenu();
              if (updatedData.data) {
                setTableData(
                  mapListMenuResponseToListMenu(updatedData.data.data)
                );
                scheduleSettingChangedNotify();
              }
            },
            onError: (error) => {
              console.error("Error updating menu:", error);
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
    <dialog id="tableEdit" className="modal">
      <div className="modal-box w-full max-w-7xl">
        <h3 className="font-bold text-lg mb-4">{selectedItem.name}</h3>
        <div className="flex">
          <div
            className="w-1/3 p-4 bg-gray-100 rounded-lg mr-4"
            style={{ maxHeight: "800px", overflowY: "auto" }} // 独立スクロール
          >
            <h4 className="font-bold mb-2">Presets</h4>
            <ul className="space-y-2 mb-4">
              {Object.keys(presets).map((presetKey) => (
                <li
                  key={presetKey}
                  className={`flex items-center p-2 rounded shadow hover:shadow-lg cursor-pointer ${
                    selectedPreset === presetKey
                      ? "bg-blue-300 text-white"
                      : "bg-blue-100 text-blue-700"
                  }`}
                  onClick={() =>
                    handlePresetClick(presetKey as keyof typeof presets)
                  } // プリセット選択
                >
                  <span className="text-sm font-bold">{presetKey}</span>
                </li>
              ))}
            </ul>
            <h4 className="font-bold mb-2">Add Individual Experiment</h4>
            <ul className="space-y-2">
              {calib_list.map((item) => (
                <li
                  key={item}
                  className="flex items-center p-2 bg-white rounded shadow hover:shadow-lg cursor-pointer"
                  onClick={() => handleListItemClick(item)} // 個別クリックで追加
                >
                  <span className="material-icons text-blue-500 mr-2">-</span>
                  <span className="text-sm text-gray-700">{item}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="w-2/3 p-2">
            <Editor
              height="800px"
              defaultLanguage="yaml"
              value={yamlText}
              onChange={handleYamlChange}
              theme="light"
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
              <div style={{ color: "red", marginTop: "8px" }}>
                {validationError}
              </div>
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
