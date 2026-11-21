import { useEffect, useState } from "react";

/**
 * Content-box size of an element, updated on resize. Zero until it is measured.
 * `ref` is a callback ref, so the element may mount after the first render.
 */
export function useElementSize<T extends HTMLElement>() {
  const [element, ref] = useState<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      setSize((current) =>
        current.width === rect.width && current.height === rect.height
          ? current
          : { width: rect.width, height: rect.height },
      );
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  return { ref, ...size };
}

/** Grid dimensions of a topology: positions when known, else a square of `gridSize`. */
export function topologyGridDimensions(
  qubits: Record<number, { row: number; col: number }> | undefined,
  gridSize: number | undefined,
): { rows: number; cols: number } {
  if (qubits && Object.keys(qubits).length > 0) {
    let rows = 0;
    let cols = 0;
    for (const pos of Object.values(qubits)) {
      rows = Math.max(rows, pos.row + 1);
      cols = Math.max(cols, pos.col + 1);
    }
    return { rows, cols };
  }
  const size = gridSize ?? 8;
  return { rows: size, cols: size };
}

/**
 * Largest cell side, capped at `max`, at which a `rows` x `cols` grid with
 * `gap` px between cells fits into `width` x `height`. Falls back to `max`
 * before the container is measured.
 */
export function fitCellSize(
  width: number,
  height: number,
  rows: number,
  cols: number,
  { max = 60, min = 12, gap = 2 }: { max?: number; min?: number; gap?: number } = {},
): number {
  if (width <= 0 || height <= 0 || rows <= 0 || cols <= 0) return max;
  const byWidth = (width - (cols - 1) * gap) / cols;
  const byHeight = (height - (rows - 1) * gap) / rows;
  return Math.max(min, Math.min(max, Math.floor(Math.min(byWidth, byHeight))));
}
