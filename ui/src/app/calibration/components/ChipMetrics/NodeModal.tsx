"use client";

import React from "react";

type NodeModalProps = {
  id: string;
  node: any;
};

export const NodeModal: React.FC<NodeModalProps> = ({ id, node }) => {
  if (!node) return null;

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
        <p className="py-4">Status: {node.data.status}</p>
        <p className="py-4">Qubit Frequency: {node.data.qubit_frequency_cw}</p>
      </div>
    </div>
  );
};
