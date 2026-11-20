"use client";

import { type KeyboardEvent, useMemo } from "react";

import { topologyGridDimensions } from "@/components/features/custom-dashboards/panels/useElementSize";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";

/** Side of one qubit tile in SVG units. */
export const CELL = 40;
const PAD = 8;

export interface Point {
  x: number;
  y: number;
}

export interface TopologyLayout {
  /** Top-left corner of each qubit tile, keyed by the normalized qubit ID ("5"). */
  positions: Map<string, Point>;
  width: number;
  height: number;
  /** Distance between the centres of neighbouring tiles. */
  pitch: number;
  gap: number;
  muxBoxes: Array<{
    id: number;
    x: number;
    y: number;
    width: number;
    height: number;
    even: boolean;
  }>;
  isLoading: boolean;
}

/** Tile positions of a chip topology with `gap` between tiles. */
export function useTopologyLayout(topologyId: string, gap: number): TopologyLayout {
  const {
    qubits,
    gridSize,
    muxGroups = [],
    hasMux = false,
    showMuxBoundaries = false,
    isLoading,
  } = useTopologyConfig(topologyId);
  const pitch = CELL + gap;
  const { rows, cols } = topologyGridDimensions(qubits, gridSize);

  const positions = useMemo(() => {
    const map = new Map<string, Point>();
    for (const [qid, pos] of Object.entries(qubits ?? {})) {
      map.set(String(Number(qid)), { x: PAD + pos.col * pitch, y: PAD + pos.row * pitch });
    }
    return map;
  }, [qubits, pitch]);

  const muxBoxes = useMemo(
    () =>
      hasMux && showMuxBoundaries
        ? muxGroups.map((box) => ({
            id: box.muxId,
            x: PAD + box.minCol * pitch - gap / 2 + 1,
            y: PAD + box.minRow * pitch - gap / 2 + 1,
            width: (box.maxCol - box.minCol + 1) * pitch - 2,
            height: (box.maxRow - box.minRow + 1) * pitch - 2,
            even: box.isEven,
          }))
        : [],
    [gap, hasMux, muxGroups, pitch, showMuxBoundaries],
  );

  return {
    positions,
    width: cols * CELL + (cols - 1) * gap + PAD * 2,
    height: rows * CELL + (rows - 1) * gap + PAD * 2,
    pitch,
    gap,
    muxBoxes,
    isLoading,
  };
}

/** Dashed outlines of the MUX groups, when the topology defines them. */
export function MuxBoxes({ boxes }: { boxes: TopologyLayout["muxBoxes"] }) {
  return (
    <>
      {boxes.map((box) => (
        <rect
          key={box.id}
          x={box.x}
          y={box.y}
          width={box.width}
          height={box.height}
          rx={6}
          fill="none"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          className={box.even ? "stroke-primary/30" : "stroke-secondary/30"}
        >
          <title>{`MUX${box.id}`}</title>
        </rect>
      ))}
    </>
  );
}

/** Keyboard handler that runs `handler` on Enter or Space, for SVG elements with role=button. */
export function onActivate(handler: () => void) {
  return (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handler();
    }
  };
}
