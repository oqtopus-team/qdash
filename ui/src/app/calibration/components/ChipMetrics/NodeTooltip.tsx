"use client";

import React, { useEffect, useState } from "react";

type NodeTooltipProps = {
  id: string;
  node: any;
};

export const NodeTooltip: React.FC<NodeTooltipProps> = ({ id, node }) => {
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});

  useEffect(() => {
    if (node) {
      const { x, y } = node.position;
      setTooltipStyle({
        position: "absolute",
        top: `${y}px`,
        left: `${x}px`,
        transform: "translate(-50%, -100%)",
        zIndex: 1000,
        backgroundColor: "white",
        padding: "10px",
        borderRadius: "8px",
        boxShadow: "0 4px 8px rgba(0, 0, 0, 0.1)",
      });
    }
  }, [node]);

  if (!node) return null;

  return (
    <div id={id} style={tooltipStyle}>
      <h3 className="font-bold text-lg">{node.label}</h3>
      <p className="py-4">Status: {node.data.status}</p>
      <p className="py-4">Qubit Frequency: {node.data.qubit_frequency_cw}</p>
    </div>
  );
};
