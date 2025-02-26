"use client";

import React from "react";

type EdgeModalProps = {
  id: string;
  edge: any;
};

export const EdgeModal: React.FC<EdgeModalProps> = ({ id, edge }) => {
  if (!edge) return null;

  return (
    <div
      id={id}
      className="modal"
      style={{
        display: "block",
        position: "fixed", // fixedに変更
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
        <p className="py-4">Coupling Strength: {edge.data.coupling_strength}</p>
      </div>
    </div>
  );
};
