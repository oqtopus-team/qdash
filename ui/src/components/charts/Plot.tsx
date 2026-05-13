"use client";

import { useEffect, useRef } from "react";
import type { CSSProperties } from "react";

import type {
  Config,
  Layout,
  PlotHoverEvent,
  PlotMouseEvent,
  PlotRelayoutEvent,
  PlotSelectionEvent,
} from "plotly.js";
import Plotly from "plotly.js-dist-min";

interface PlotFigure {
  data: Plotly.Data[];
  layout: Partial<Layout>;
  frames: unknown[];
}

interface PlotProps {
  data: Plotly.Data[];
  layout?: Partial<Layout>;
  config?: Partial<Config>;
  style?: CSSProperties;
  className?: string;
  useResizeHandler?: boolean;
  onInitialized?: (figure: PlotFigure, graphDiv: HTMLElement) => void;
  onUpdate?: (figure: PlotFigure, graphDiv: HTMLElement) => void;
  onPurge?: (figure: PlotFigure, graphDiv: HTMLElement) => void;
  onSelected?: (event: PlotSelectionEvent) => void;
  onClick?: (event: PlotMouseEvent) => void;
  onHover?: (event: PlotHoverEvent) => void;
  onUnhover?: (event: PlotHoverEvent) => void;
  onRelayout?: (event: PlotRelayoutEvent) => void;
}

const typedPlotly = Plotly as unknown as {
  Plots: { resize: (div: HTMLElement) => void };
  react: (
    div: HTMLElement,
    data: PlotProps["data"],
    layout?: PlotProps["layout"],
    config?: PlotProps["config"],
  ) => Promise<HTMLElement>;
  purge: (div: HTMLElement) => void;
};

export default function Plot({
  data,
  layout,
  config,
  style,
  className,
  useResizeHandler = false,
  onInitialized,
  onUpdate,
  onPurge,
  onSelected,
  onClick,
  onHover,
  onUnhover,
  onRelayout,
}: PlotProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isInitializedRef = useRef(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;

    void typedPlotly.react(container, data, layout, config).then((graphDiv) => {
      if (cancelled) return;

      const figure: PlotFigure = {
        data,
        layout: layout ?? {},
        frames: [],
      };

      if (!isInitializedRef.current) {
        isInitializedRef.current = true;
        onInitialized?.(figure, graphDiv);
      } else {
        onUpdate?.(figure, graphDiv);
      }

      const emitter = graphDiv as HTMLElement & {
        on?: (event: string, handler: (...args: unknown[]) => void) => void;
        removeAllListeners?: (event?: string) => void;
      };
      emitter.removeAllListeners?.("plotly_selected");
      emitter.removeAllListeners?.("plotly_click");
      emitter.removeAllListeners?.("plotly_hover");
      emitter.removeAllListeners?.("plotly_unhover");
      emitter.removeAllListeners?.("plotly_relayout");
      if (onSelected)
        emitter.on?.(
          "plotly_selected",
          onSelected as (...args: unknown[]) => void,
        );
      if (onClick)
        emitter.on?.("plotly_click", onClick as (...args: unknown[]) => void);
      if (onHover)
        emitter.on?.("plotly_hover", onHover as (...args: unknown[]) => void);
      if (onUnhover)
        emitter.on?.(
          "plotly_unhover",
          onUnhover as (...args: unknown[]) => void,
        );
      if (onRelayout)
        emitter.on?.(
          "plotly_relayout",
          onRelayout as (...args: unknown[]) => void,
        );
    });

    return () => {
      cancelled = true;
    };
  }, [
    config,
    data,
    layout,
    onClick,
    onHover,
    onInitialized,
    onRelayout,
    onSelected,
    onUnhover,
    onUpdate,
  ]);

  useEffect(() => {
    if (!useResizeHandler) return;

    const container = containerRef.current;
    if (!container) return;

    const resize = () => typedPlotly.Plots.resize(container);
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    observer?.observe(container);
    window.addEventListener("resize", resize);

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, [useResizeHandler]);

  useEffect(() => {
    const container = containerRef.current;

    return () => {
      if (!container) return;
      const figure: PlotFigure = {
        data,
        layout: layout ?? {},
        frames: [],
      };
      onPurge?.(figure, container);
      typedPlotly.purge(container);
    };
  }, [data, layout, onPurge]);

  return <div ref={containerRef} style={style} className={className} />;
}
