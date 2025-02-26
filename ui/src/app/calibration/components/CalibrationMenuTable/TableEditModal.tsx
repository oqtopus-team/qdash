"use client";

import "react18-json-view/src/style.css";
import { toast } from "react-toastify";
import yaml from "js-yaml";
import { useEffect, useState } from "react";
import { useTheme } from "@/app/hooks/useTheme";
import Editor from "@monaco-editor/react";

import { mapListMenuResponseToListMenu } from "../../model";
import { useUpdateMenu } from "@/client/menu/menu";

import type { Menu } from "../../model";
import type { UseQueryResult } from "@tanstack/react-query";
import type { UpdateMenuRequest } from "@/schemas";

interface YamlData {
  name: string;
  description: string;
  one_qubit_calib_plan: number[][];
  two_qubit_calib_plan: [number, number][][];
  mode: string;
  notify_bool: boolean;
  flow: string[];
  tags?: string[];
  exp_list?: string[];
}

// YAML 形式でデータを生成する関数
function generateYamlWithCustomArrayFormat(data: Menu): string {
  return `
name: ${data.name}
description: ${data.description}
one_qubit_calib_plan:
${data.one_qubit_calib_plan
  .map((seq) => `  - ${JSON.stringify(seq)}`)
  .join("\n")}
two_qubit_calib_plan:
${data.two_qubit_calib_plan
  .map((pair) => `  - [${pair[0]}, ${pair[1]}]`)
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
    "CheckT2Echo",
    "CheckEffectiveQubitFrequency",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "ReadoutClassification",
    "RandomizedBenchmarking",
    "X90InterleavedRandomizedBenchmarking",
    "X180InterleavedRandomizedBenchmarking",
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
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
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

  const handlePresetClick = (presetKey: keyof typeof presets) => {
    try {
      const updatedYaml = yaml.load(yamlText) as YamlData;
      updatedYaml.exp_list = presets[presetKey];
      updatedYaml.mode = presetKey;
      setYamlText(generateYamlWithCustomArrayFormat(updatedYaml as Menu));
      setValidationError("");
      setSelectedPreset(presetKey);
    } catch (error) {
      console.error("YAMLパースエラー:", error);
      toast.error("プリセットの適用に失敗しました");
    }
  };

  const handleListItemClick = (item: string) => {
    try {
      const updatedYaml = yaml.load(yamlText) as YamlData;
      if (!updatedYaml.exp_list) {
        updatedYaml.exp_list = [];
      }
      updatedYaml.exp_list.push(item);
      setYamlText(generateYamlWithCustomArrayFormat(updatedYaml as Menu));
      setValidationError("");
      setSelectedPreset(null);
    } catch (error) {
      console.error("YAMLパースエラー:", error);
      toast.error("エディタ内容の更新に失敗しました");
    }
  };

  const handleSaveClick = async () => {
    try {
      const rawData = yaml.load(yamlText) as any;

      // Ensure two_qubit_calib_plan is properly formatted
      const updatedItem: YamlData = {
        ...rawData,
        two_qubit_calib_plan: (rawData.two_qubit_calib_plan as number[][]).map(
          (pair) => {
            if (
              !Array.isArray(pair) ||
              pair.length !== 2 ||
              !pair.every((n) => typeof n === "number")
            ) {
              throw new Error(
                "Invalid two_qubit_calib_plan format. Each pair must be [number, number]"
              );
            }
            return pair as [number, number];
          }
        ),
      };

      if (updatedItem.mode !== "custom") {
        const allPresetItems = Object.values(presets).flat();
        const invalidItems =
          updatedItem.exp_list?.filter(
            (item) => !allPresetItems.includes(item)
          ) ?? [];

        if (invalidItems.length > 0) {
          setValidationError(
            `exp_list に無効な項目が含まれています: ${invalidItems.join(", ")}`
          );
          return;
        }
      }

      const formattedItem: UpdateMenuRequest = {
        name: updatedItem.name,
        description: updatedItem.description,
        one_qubit_calib_plan: updatedItem.one_qubit_calib_plan,
        two_qubit_calib_plan: updatedItem.two_qubit_calib_plan,
        mode: updatedItem.mode,
        notify_bool: updatedItem.notify_bool,
        flow: updatedItem.flow,
        tags:
          updatedItem.tags?.filter((item) => item !== null && item !== "") ??
          [],
        exp_list:
          updatedItem.exp_list?.filter(
            (item) => item !== null && item !== ""
          ) ?? [],
      };

      const menuItem: Menu = {
        name: updatedItem.name,
        description: updatedItem.description,
        one_qubit_calib_plan: updatedItem.one_qubit_calib_plan,
        two_qubit_calib_plan: updatedItem.two_qubit_calib_plan,
        mode: updatedItem.mode,
        notify_bool: updatedItem.notify_bool,
        flow: updatedItem.flow,
        tags:
          updatedItem.tags?.filter((item) => item !== null && item !== "") ??
          [],
        exp_list:
          updatedItem.exp_list?.filter(
            (item) => item !== null && item !== ""
          ) ?? [],
      };

      setSelectedItem(menuItem);

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
            className="w-1/3 p-4 bg-base-200 rounded-lg mr-4"
            style={{ maxHeight: "800px", overflowY: "auto" }}
          >
            <h4 className="font-bold mb-2">Presets</h4>
            <ul className="space-y-2 mb-4">
              {Object.keys(presets).map((presetKey) => (
                <li
                  key={presetKey}
                  className={`flex items-center p-2 rounded shadow hover:shadow-lg cursor-pointer ${
                    selectedPreset === presetKey
                      ? "bg-primary/30 text-primary-content"
                      : "bg-primary/10 text-primary"
                  }`}
                  onClick={() =>
                    handlePresetClick(presetKey as keyof typeof presets)
                  }
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
                  className="flex items-center p-2 bg-base-100 rounded shadow hover:shadow-lg cursor-pointer"
                  onClick={() => handleListItemClick(item)}
                >
                  <span className="material-icons text-primary mr-2">-</span>
                  <span className="text-sm text-base-content/70">{item}</span>
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
