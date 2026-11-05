import { vi } from "vitest";

// next/font only exists as an SWC transform, so the geist entry points cannot load under Vitest.
const fontStub = (name: string) => ({
  className: "",
  variable: `--font-${name}`,
  style: { fontFamily: name },
});
vi.mock("geist/font/sans", () => ({ GeistSans: fontStub("geist-sans") }));
vi.mock("geist/font/mono", () => ({ GeistMono: fontStub("geist-mono") }));

import "@testing-library/jest-dom/vitest";

class ResizeObserverMock implements ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverMock;
HTMLElement.prototype.scrollIntoView = () => undefined;

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});
