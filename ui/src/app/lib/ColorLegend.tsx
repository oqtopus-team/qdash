"use client";

import { useEffect, useRef } from "react";

interface ColorLegendProps {
  colorScale: string[];
  labels: string[];
  title?: string;
  tickFormat?: (d: number) => string;
  width?: number;
  height?: number;
  marginTop?: number;
  marginRight?: number;
  marginBottom?: number;
  marginLeft?: number;
  tickSize?: number;
}

export function ColorLegend({
  colorScale,
  labels,
  title,
  tickFormat = (x) => x.toString(),
  width = 320,
  tickSize = 6,
  height = 44 + 6, // Using fixed value instead of tickSize
  marginTop = 18,
  marginRight = 0,
  marginBottom = 16 + 6, // Using fixed value instead of tickSize
  marginLeft = 0,
}: ColorLegendProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext("2d");
    if (!context) return;

    // Clear canvas
    context.clearRect(0, 0, width, height);

    // Draw title if provided
    if (title) {
      context.textAlign = "center";
      context.textBaseline = "top";
      context.fillStyle = "currentColor";
      context.font = "10px sans-serif";
      context.fillText(title, width / 2, marginTop);
    }

    // Draw color scale
    const x = marginLeft;
    const y = height - marginBottom;
    const w = width - marginLeft - marginRight;
    const h = 8;

    // Create gradient
    const gradient = context.createLinearGradient(x, 0, x + w, 0);
    colorScale.forEach((color, i) => {
      gradient.addColorStop(i / (colorScale.length - 1), color);
    });

    // Draw gradient bar
    context.fillStyle = gradient;
    context.fillRect(x, y - h, w, h);

    // Draw ticks and labels
    context.textAlign = "center";
    context.textBaseline = "top";
    context.fillStyle = "currentColor";
    context.font = "10px sans-serif";

    labels.forEach((label, i) => {
      const xPos = x + (i * w) / (labels.length - 1);
      context.beginPath();
      context.moveTo(xPos, y);
      context.lineTo(xPos, y + tickSize);
      context.stroke();
      context.fillText(label, xPos, y + tickSize);
    });
  }, [
    colorScale,
    labels,
    title,
    tickFormat,
    width,
    height,
    marginTop,
    marginRight,
    marginBottom,
    marginLeft,
    tickSize,
  ]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{ width, height }}
    />
  );
}
