"use client";

import React from "react";

import type { OutputParameterModel } from "@/schemas/outputParameterModel";

interface ParameterData extends OutputParameterModel {
  value_type?: string;
  unit?: string;
}

interface NodeData {
  status: string;
  qubit_frequency_cw: ParameterData;
  // 他のパラメータもここに追加
}

type NodeModalProps = {
  id: string;
  node: {
    label: string;
    position: { x: number; y: number };
    data: NodeData;
  };
};

export const NodeModal: React.FC<NodeModalProps> = ({ id, node }) => {
  if (!node) return null;

  const renderParameterValue = (param?: ParameterData) => {
    if (!param?.value) return "N/A";

    let display = `${param.value}`;
    if (param.unit) {
      display += ` ${param.unit}`;
    }
    if (param.error !== undefined) {
      display += ` ±${param.error}`;
      if (param.unit) {
        display += ` ${param.unit}`;
      }
    }
    return display;
  };

  return (
    <div
      id={id}
      className="modal modal-open"
      style={{
        position: "absolute",
        top: `${node.position.y}px`,
        left: `${node.position.x}px`,
        transform: "translate(-50%, -50%)",
        zIndex: 1000,
        backgroundColor: "white",
        padding: "10px",
        borderRadius: "8px",
        boxShadow: "0 4px 8px rgba(0, 0, 0, 0.1)",
      }}
    >
      <div className="modal-box">
        <h3 className="font-bold text-lg">{node.label}</h3>
        <div className="space-y-2">
          <p className="py-2">Status: {node.data.status}</p>
          <div className="flex flex-col gap-1">
            <p className="font-medium">Qubit Frequency:</p>
            <p className="pl-4">
              {renderParameterValue(node.data.qubit_frequency_cw)}
            </p>
            {node.data.qubit_frequency_cw?.description && (
              <p className="text-sm text-gray-500 pl-4">
                {node.data.qubit_frequency_cw.description}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
