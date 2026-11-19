import { expect, it } from "vitest";
import { startDiagramPan, zoomDiagram } from "@/lib/chatMermaidView";

it("preserves wheel zoom translation during an ongoing drag", () => {
  const viewport = document.createElement("div");
  viewport.innerHTML = "<div data-mermaid-canvas></div>";
  const canvas = viewport.firstElementChild as HTMLElement;
  startDiagramPan(
    viewport,
    {
      button: 0,
      pointerId: 1,
      clientX: 0,
      clientY: 0,
      preventDefault() {},
    } as PointerEvent,
    { always: true },
  );
  const move = (x: number) => {
    const event = new Event("pointermove");
    Object.assign(event, { pointerId: 1, clientX: x, clientY: 0 });
    viewport.dispatchEvent(event);
  };
  move(10);
  expect(canvas.dataset.x).toBe("10");
  zoomDiagram(viewport, 1.25, 100, 0);
  const afterZoom = Number(canvas.dataset.x);
  move(20);
  expect(Number(canvas.dataset.x)).toBe(afterZoom + 10);
  expect(canvas.dataset.scale).toBe("1.25");
});
