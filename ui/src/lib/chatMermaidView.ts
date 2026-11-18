/**
 * Pan and zoom for a rendered diagram. The view state lives on the canvas
 * element, so it works on markup the Markdown renderer owns as well as on the
 * fullscreen dialog's own copy.
 */

const MIN_SCALE = 0.25;
const MAX_SCALE = 8;
export const ZOOM_STEP = 1.25;

interface View {
  scale: number;
  x: number;
  y: number;
}

function canvasOf(viewport: HTMLElement): HTMLElement | null {
  return viewport.querySelector<HTMLElement>("[data-mermaid-canvas]");
}

function readView(canvas: HTMLElement): View {
  return {
    scale: Number(canvas.dataset.scale ?? 1),
    x: Number(canvas.dataset.x ?? 0),
    y: Number(canvas.dataset.y ?? 0),
  };
}

function writeView(viewport: HTMLElement, canvas: HTMLElement, view: View): void {
  canvas.dataset.scale = String(view.scale);
  canvas.dataset.x = String(view.x);
  canvas.dataset.y = String(view.y);
  const moved = view.scale !== 1 || view.x !== 0 || view.y !== 0;
  canvas.style.transform = moved ? `translate(${view.x}px, ${view.y}px) scale(${view.scale})` : "";
  viewport.toggleAttribute("data-zoomed", moved);
}

/** Zoom by `factor`, keeping the point at (originX, originY) of the viewport in place. */
export function zoomDiagram(
  viewport: HTMLElement,
  factor: number,
  originX = viewport.clientWidth / 2,
  originY = viewport.clientHeight / 2,
): void {
  const canvas = canvasOf(viewport);
  if (!canvas) return;
  const view = readView(canvas);
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
  const ratio = scale / view.scale;
  // The canvas scales around its center, so offsets are measured from the viewport center.
  const cx = originX - viewport.clientWidth / 2;
  const cy = originY - viewport.clientHeight / 2;
  writeView(viewport, canvas, {
    scale,
    x: cx - (cx - view.x) * ratio,
    y: cy - (cy - view.y) * ratio,
  });
}

export function resetDiagram(viewport: HTMLElement): void {
  const canvas = canvasOf(viewport);
  if (canvas) writeView(viewport, canvas, { scale: 1, x: 0, y: 0 });
}

/**
 * Drag the diagram with the pointer. Inline diagrams pan only once zoomed, so
 * a touch on an unzoomed diagram still scrolls the conversation.
 */
export function startDiagramPan(
  viewport: HTMLElement,
  event: PointerEvent,
  { always = false } = {},
): void {
  if (event.button !== 0 || (!always && !viewport.hasAttribute("data-zoomed"))) return;
  const canvas = canvasOf(viewport);
  if (!canvas) return;
  const start = readView(canvas);
  const { clientX, clientY, pointerId } = event;
  viewport.setPointerCapture?.(pointerId);
  viewport.setAttribute("data-panning", "");
  const move = (next: PointerEvent) => {
    if (next.pointerId !== pointerId) return;
    writeView(viewport, canvas, {
      ...readView(canvas),
      x: start.x + next.clientX - clientX,
      y: start.y + next.clientY - clientY,
    });
  };
  const end = (next: PointerEvent) => {
    if (next.pointerId !== pointerId) return;
    viewport.removeAttribute("data-panning");
    viewport.removeEventListener("pointermove", move);
    viewport.removeEventListener("pointerup", end);
    viewport.removeEventListener("pointercancel", end);
  };
  viewport.addEventListener("pointermove", move);
  viewport.addEventListener("pointerup", end);
  viewport.addEventListener("pointercancel", end);
  event.preventDefault();
}
