import React, { useEffect, useState } from "react";

type EdgeTooltipProps = {
  id: string;
  edge: any;
};

export const EdgeTooltip: React.FC<EdgeTooltipProps> = ({ id, edge }) => {
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});

  useEffect(() => {
    if (edge) {
      const { x, y } = edge.position;
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
  }, [edge]);

  if (!edge) return null;

  return (
    <div id={id} style={tooltipStyle}>
      <h3 className="font-bold text-lg">{edge.label}</h3>
      <p className="py-4">Coupling Strength: {edge.data.coupling_strength}</p>
    </div>
  );
};
