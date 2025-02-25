"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import clsx from "clsx";
import type { OneQubitCalib, TwoQubitCalib } from "../../model";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div className="absolute inset-0 flex items-center justify-center bg-white z-10">
      <div className="text-gray-500">Loading graph...</div>
    </div>
  ),
});

interface ChipMetricsGraphProps {
  oneQubitCalibInfo: OneQubitCalib[];
  twoQubitCalibInfo: TwoQubitCalib[];
  onNodePointerOver: (node: any) => void;
  onEdgePointerOver: (edge: any) => void;
}

type NodeObject = {
  id: string;
  label: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
  fill?: string;
  data?: any;
};

type ForceGraphNode = {
  id: string | number;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
  [key: string]: any;
};

type ForceGraphLink = {
  source: string | number;
  target: string | number;
  [key: string]: any;
};

const scalePosition = (position: number, scale: number = 100): number => {
  return position * scale;
};

const normalizePositions = (nodes: NodeObject[]): NodeObject[] => {
  // 位置の範囲を計算
  const positions = nodes.map((node) => ({
    x: node.data.position?.x ?? 0,
    y: node.data.position?.y ?? 0,
  }));

  const minX = Math.min(...positions.map((p) => p.x));
  const maxX = Math.max(...positions.map((p) => p.x));
  const minY = Math.min(...positions.map((p) => p.y));
  const maxY = Math.max(...positions.map((p) => p.y));

  // 中心点を計算
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;

  // スケーリングと中心化を適用
  return nodes.map((node) => {
    const x = scalePosition((node.data.position?.x ?? 0) - centerX);
    const y = scalePosition((node.data.position?.y ?? 0) - centerY);
    return {
      ...node,
      x,
      y,
      fx: x,
      fy: y,
    };
  });
};

export function ChipMetricsGraph({
  oneQubitCalibInfo,
  twoQubitCalibInfo,
  onNodePointerOver,
  onEdgePointerOver,
}: ChipMetricsGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const [containerSize, setContainerSize] = useState<{
    width: number;
    height: number;
  }>({ width: 800, height: 600 });
  const [isReady, setIsReady] = useState(false);

  const updateSize = useCallback(() => {
    if (containerRef.current) {
      setContainerSize({
        width: containerRef.current.offsetWidth,
        height: containerRef.current.offsetHeight,
      });
    }
  }, []);

  useEffect(() => {
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, [updateSize]);

  const nodes = oneQubitCalibInfo.map((node) => ({
    id: node.id,
    label: node.label,
    fill: node.fill,
    data: node.data,
  }));

  const links = twoQubitCalibInfo.map((edge) => ({
    id: `${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    fill: edge.fill,
    data: edge.data,
  }));

  const normalizedNodes = normalizePositions(nodes);

  const initializeGraph = useCallback(() => {
    if (graphRef.current) {
      // 物理シミュレーションを制御
      graphRef.current
        .d3Force("charge", null)
        .d3Force("center", null)
        .d3Force("collide", null)
        .d3Force("link", null);

      // グラフを中央に配置
      requestAnimationFrame(() => {
        if (graphRef.current) {
          graphRef.current.zoomToFit(400, 50);
          setIsReady(true);
        }
      });
    }
  }, []);

  useEffect(() => {
    setIsReady(false);
    initializeGraph();
  }, [initializeGraph, oneQubitCalibInfo, twoQubitCalibInfo]);

  return (
    <div
      ref={containerRef}
      className={clsx("relative w-full h-full shadow-md overflow-hidden")}
      style={{ minHeight: "600px" }}
    >
      <div className={clsx("absolute inset-0", !isReady && "opacity-0")}>
        <ForceGraph2D
          ref={graphRef}
          graphData={{
            nodes: normalizedNodes,
            links,
          }}
          nodeLabel="label"
          nodeColor={(node) => (node as NodeObject).fill || "#4887fa"}
          linkColor={(link) => (link as { fill?: string }).fill || "#4887fa"}
          backgroundColor="transparent"
          nodeCanvasObject={(
            node: any,
            ctx: CanvasRenderingContext2D,
            globalScale: number
          ) => {
            const radius = 18 / globalScale;
            ctx.beginPath();
            ctx.arc(node.x || 0, node.y || 0, radius, 0, 2 * Math.PI, false);
            ctx.fillStyle = (node as NodeObject).fill || "#4887fa";
            ctx.fill();
            ctx.strokeStyle = "white";
            ctx.lineWidth = 1;
            ctx.stroke();

            const label = (node as NodeObject).label || "";
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px Arial Bold`;
            ctx.fillStyle = "white";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(label, node.x || 0, node.y || 0);
          }}
          linkWidth={8}
          onNodeHover={(node) => {
            if (node) {
              onNodePointerOver(node);
            }
          }}
          onLinkHover={(link) => {
            if (link) {
              onEdgePointerOver({
                source: (link as ForceGraphLink).source,
                target: (link as ForceGraphLink).target,
                ...((link as ForceGraphLink).data || {}),
              });
            }
          }}
          width={containerSize.width}
          height={containerSize.height}
          enableNodeDrag={false}
          enableZoomInteraction={true}
          enablePanInteraction={true}
          d3AlphaDecay={1}
          d3VelocityDecay={1}
          cooldownTime={0}
        />
      </div>
    </div>
  );
}
