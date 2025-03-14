"use client";

import React from "react";

import { OutputParameterModel } from "@/schemas/outputParameterModel";

interface ParameterData extends OutputParameterModel {
  value_type?: string;
  unit?: string;
}

interface EdgeData {
  coupling_strength: ParameterData;
  // 他のパラメータもここに追加
}

type EdgeModalProps = {
  id: string;
  edge: {
    label: string;
    position: { x: number; y: number };
    data: EdgeData;
  };
};

export const EdgeModal: React.FC<EdgeModalProps> = ({ id, edge }) => {
  if (!edge) return null;

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
      className="modal"
      style={{
        display: "block",
        position: "fixed",
        top: `${edge.position.y}px`,
        left: `${edge.position.x}px`,
        transform: "translate(-50%, -50%)",
        zIndex: 1000,
        backgroundColor: "white",
        padding: "10px",
        borderRadius: "8px",
        boxShadow: "0 4px 8px rgba(0, 0, 0, 0.1)",
      }}
    >
      <div className="modal-box">
        <h3 className="font-bold text-lg">{edge.label}</h3>
        <div className="space-y-2">
          <div className="flex flex-col gap-1">
            <p className="font-medium">Coupling Strength:</p>
            <p className="pl-4">
              {renderParameterValue(edge.data.coupling_strength)}
            </p>
            {edge.data.coupling_strength?.description && (
              <p className="text-sm text-gray-500 pl-4">
                {edge.data.coupling_strength.description}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
