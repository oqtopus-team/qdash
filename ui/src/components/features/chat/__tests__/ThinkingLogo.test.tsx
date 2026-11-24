import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@/contexts/ThemeContext";

import {
  ASSEMBLED_AT,
  ThinkingLogo,
  adaptTint,
  logoFrame,
  resolveBrandTint,
  smallness,
  tintedInk,
} from "../ThinkingLogo";

interface Arc {
  x: number;
  y: number;
  fill: string;
}

/** A 2D context that records each dot it is asked to draw. */
function stubCanvas() {
  const frames: Arc[][] = [];
  let current: Arc[] = [];
  let fillStyle = "";
  const ctx = {
    setTransform: vi.fn(),
    clearRect: vi.fn(() => {
      current = [];
      frames.push(current);
    }),
    beginPath: vi.fn(),
    fill: vi.fn(),
    arc: vi.fn((x: number, y: number) => current.push({ x, y, fill: fillStyle })),
    fillRect: vi.fn(),
    getImageData: vi.fn(() => ({ data: [0, 0, 0, 0] })),
    get fillStyle() {
      return fillStyle;
    },
    set fillStyle(value: string) {
      fillStyle = value;
    },
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    ctx as unknown as CanvasRenderingContext2D,
  );
  return { ctx, frames };
}

function setReducedMotion(reduced: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: reduced && query === "(prefers-reduced-motion: reduce)",
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

const rgb = (fill: string) =>
  fill
    .match(/\d+(\.\d+)?/g)!
    .slice(0, 3)
    .map(Number);

let observers: { callback: IntersectionObserverCallback; disconnect: ReturnType<typeof vi.fn> }[];

beforeEach(() => {
  observers = [];
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      disconnect = vi.fn();
      observe = vi.fn();
      constructor(callback: IntersectionObserverCallback) {
        observers.push({ callback, disconnect: this.disconnect });
      }
    },
  );
  vi.stubGlobal(
    "requestAnimationFrame",
    vi.fn(() => 7),
  );
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("ThinkingLogo", () => {
  it("is decorative and draws all 495 dots of the mark", () => {
    setReducedMotion(false);
    const { frames } = stubCanvas();
    render(<ThinkingLogo />);
    const canvas = screen.getByTestId("thinking-logo");
    expect(canvas).toHaveAttribute("aria-hidden", "true");
    expect(canvas.style.width).toBe("24px");
    expect(frames[0]).toHaveLength(495);
  });

  it("shows the assembled mark face-on as one still frame under reduced motion", () => {
    setReducedMotion(true);
    const { frames } = stubCanvas();
    render(<ThinkingLogo size={18} />);

    expect(screen.getByTestId("thinking-logo")).toHaveAttribute("data-motion", "still");
    expect(requestAnimationFrame).not.toHaveBeenCalled();
    expect(observers).toHaveLength(0);
    expect(frames).toHaveLength(1);
    // The first artwork point (0.191, 0.793) sits at its baked place: centre 9, radius 9 * 0.82.
    const R = 9 * 0.82;
    expect(
      frames[0].some(
        (d) => Math.abs(d.x - (9 + 0.191 * R)) < 1e-3 && Math.abs(d.y - (9 - 0.793 * R)) < 1e-3,
      ),
    ).toBe(true);
  });

  it("pauses offscreen and on a hidden tab, and releases everything on unmount", () => {
    setReducedMotion(false);
    stubCanvas();
    const removeListener = vi.spyOn(document, "removeEventListener");
    const { unmount } = render(<ThinkingLogo />);
    expect(screen.getByTestId("thinking-logo")).toHaveAttribute("data-motion", "animated");
    expect(observers).toHaveLength(1);
    const [io] = observers;
    const entry = (isIntersecting: boolean) =>
      [{ isIntersecting }] as unknown as IntersectionObserverEntry[];

    act(() => io.callback(entry(true), {} as IntersectionObserver));
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);

    act(() => io.callback(entry(false), {} as IntersectionObserver));
    expect(cancelAnimationFrame).toHaveBeenCalledWith(7);

    act(() => io.callback(entry(true), {} as IntersectionObserver));
    expect(requestAnimationFrame).toHaveBeenCalledTimes(2);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(cancelAnimationFrame).toHaveBeenCalledTimes(2);

    unmount();
    expect(io.disconnect).toHaveBeenCalled();
    expect(removeListener).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
  });

  it("paints in the dark theme's brand colour, scaled by depth", async () => {
    localStorage.setItem("theme", "dark");
    setReducedMotion(true);
    const { frames } = stubCanvas();
    render(
      <ThemeProvider>
        <ThinkingLogo />
      </ThemeProvider>,
    );
    // The provider settles on the saved theme after mount and the mark repaints.
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    const fills = frames[frames.length - 1].map((d) => rgb(d.fill));
    // Dark substrate: every dot is the brand blue #7f9fdc scaled toward black, so the hue
    // holds while the brightness varies with depth.
    for (const [r, g, b] of fills) {
      expect(r / b).toBeCloseTo(0x7f / 0xdc, 1);
      expect(g / b).toBeCloseTo(0x9f / 0xdc, 1);
    }
    expect(new Set(fills.map(([, , b]) => b)).size).toBeGreaterThan(10);
  });
});

describe("small-mark legibility", () => {
  // Mid-dwell: the dots sit on the turning sphere, before any morph.
  const SPHERE_AT = 2;

  it("eases in below 48px and leaves large marks untouched", () => {
    expect(smallness(96)).toBe(0);
    expect(smallness(48)).toBe(0);
    expect(smallness(24)).toBeCloseTo(0.8);
    expect(smallness(18)).toBe(1);
    // At 96px the sphere keeps every dot fully opaque, as the playground tuning draws it.
    expect(logoFrame(96, SPHERE_AT).every((d) => d.a === 1)).toBe(true);
  });

  it("fades the sphere's back hemisphere at 24px so it does not read as a flat disc", () => {
    const dots = logoFrame(24, SPHERE_AT);
    expect(dots).toHaveLength(495);
    // Draw order is back to front.
    const back = dots.slice(0, 100);
    const front = dots.slice(-100);
    const mean = (ds: typeof dots) => ds.reduce((s, d) => s + d.a, 0) / ds.length;
    expect(mean(back)).toBeLessThan(0.4);
    expect(mean(front)).toBeGreaterThan(0.85);
    // Nearer dots ink closer to the full tint than at 96px, on both substrates.
    const nearest = (size: number) => {
      const dots = logoFrame(size, SPHERE_AT);
      return dots[dots.length - 1].white;
    };
    expect(nearest(24)).toBeLessThan(nearest(96));
  });

  it("keeps the assembled mark whole and its dots large enough to anti-alias", () => {
    const mark = logoFrame(24, ASSEMBLED_AT);
    expect(mark).toHaveLength(495);
    expect(mark.every((d) => d.a > 0.99)).toBe(true);
    expect(Math.min(...mark.map((d) => d.r))).toBeGreaterThanOrEqual(0.45);
  });
});

describe("brand tint", () => {
  it("ramps from the brand colour to the substrate by ink value", () => {
    const tint = { r: 0x3d, g: 0x5a, b: 0x99 };
    expect(tintedInk(tint, 0, false, 1)).toBe("rgba(61,90,153,1)");
    expect(tintedInk(tint, 1, false, 1)).toBe("rgba(255,255,255,1)");
    expect(tintedInk(tint, 1, true, 0.5)).toBe("rgba(0,0,0,0.5)");
    // A nearer dot (lower ink) is closer to the full tint than a farther one, on both substrates.
    const lightNear = rgb(tintedInk(tint, 0.2, false, 1));
    const lightFar = rgb(tintedInk(tint, 0.5, false, 1));
    expect(lightNear[2]).toBeLessThan(lightFar[2]);
    const darkNear = rgb(tintedInk(tint, 0.2, true, 1));
    const darkFar = rgb(tintedInk(tint, 0.5, true, 1));
    expect(darkNear[2]).toBeGreaterThan(darkFar[2]);
  });

  it("lightens a dark tint on dark themes and keeps the QDash primaries", () => {
    const black = adaptTint({ r: 0, g: 0, b: 0 }, true);
    expect(black.r).toBeGreaterThan(100);
    expect(adaptTint({ r: 0x7f, g: 0x9f, b: 0xdc }, true)).toEqual({ r: 0x7f, g: 0x9f, b: 0xdc });
    expect(adaptTint({ r: 0x3d, g: 0x5a, b: 0x99 }, false)).toEqual({ r: 0x3d, g: 0x5a, b: 0x99 });
  });

  it("reads --color-primary from the theme and falls back to the QDash brand", () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    expect(resolveBrandTint(el, false)).toEqual({ r: 0x3d, g: 0x5a, b: 0x99 });
    expect(resolveBrandTint(el, true)).toEqual({ r: 0x7f, g: 0x9f, b: 0xdc });
    el.style.setProperty("--color-primary", "#2b7350");
    expect(resolveBrandTint(el, false)).toEqual({ r: 0x2b, g: 0x73, b: 0x50 });
    el.style.setProperty("--color-primary", "rgb(20, 40, 60)");
    // Too dark for a dark substrate: lightened, hue order kept.
    const dark = resolveBrandTint(el, true);
    expect(dark.r).toBeLessThan(dark.g);
    expect(dark.g).toBeLessThan(dark.b);
    expect(dark.b).toBeGreaterThan(60);
    el.remove();
  });
});
