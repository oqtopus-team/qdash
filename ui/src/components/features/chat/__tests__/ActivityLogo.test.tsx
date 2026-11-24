import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@/contexts/ThemeContext";

import {
  ACTIVITY_LOGO_MODES,
  ASSEMBLED_AT,
  ActivityLogo,
  POINTS,
  adaptTint,
  logoFrame,
  resolveBrandTint,
  smallness,
  tintedInk,
} from "../ActivityLogo";

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

describe("ActivityLogo", () => {
  it("is decorative, fits a 20px text line and draws the 244 baked dots", () => {
    setReducedMotion(false);
    const { frames } = stubCanvas();
    render(<ActivityLogo />);
    const canvas = screen.getByTestId("activity-logo");
    expect(canvas).toHaveAttribute("aria-hidden", "true");
    expect(canvas).toHaveAttribute("data-mode", "thinking");
    expect(canvas.style.width).toBe("20px");
    expect(canvas.style.height).toBe("20px");
    // No negative margin: the mark takes real layout space instead of overhanging its slot.
    expect(canvas.className).toBe("");
    expect(frames[0]).toHaveLength(244);
  });

  it.each(ACTIVITY_LOGO_MODES)(
    "shows the same assembled mark as one still frame under reduced motion (%s)",
    (mode) => {
      setReducedMotion(true);
      const { frames } = stubCanvas();
      render(<ActivityLogo mode={mode} size={18} />);
      const canvas = screen.getByTestId("activity-logo");
      expect(canvas).toHaveAttribute("data-mode", mode);
      expect(canvas).toHaveAttribute("data-motion", "still");
      expect(requestAnimationFrame).not.toHaveBeenCalled();
      expect(observers).toHaveLength(0);
      expect(frames).toHaveLength(1);
      expect(frames[0]).toHaveLength(244);
      // The first artwork point (0.16, 0.777) sits at its baked place: centre 9, radius 9 * 0.82.
      const R = 9 * 0.82;
      expect(
        frames[0].some(
          (d) => Math.abs(d.x - (9 + 0.16 * R)) < 1e-3 && Math.abs(d.y - (9 - 0.777 * R)) < 1e-3,
        ),
      ).toBe(true);
    },
  );

  it("repaints in the new mode when a row changes what it is doing", () => {
    setReducedMotion(false);
    stubCanvas();
    const { rerender } = render(<ActivityLogo mode="thinking" />);
    expect(observers).toHaveLength(1);
    rerender(<ActivityLogo mode="working" />);
    expect(screen.getByTestId("activity-logo")).toHaveAttribute("data-mode", "working");
    // The previous loop's observer is released and one new loop runs.
    expect(observers[0].disconnect).toHaveBeenCalled();
    expect(observers).toHaveLength(2);
  });

  it("pauses offscreen and on a hidden tab, and releases everything on unmount", () => {
    setReducedMotion(false);
    stubCanvas();
    const removeListener = vi.spyOn(document, "removeEventListener");
    const { unmount } = render(<ActivityLogo mode="searching" />);
    expect(screen.getByTestId("activity-logo")).toHaveAttribute("data-motion", "animated");
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
        <ActivityLogo mode="waiting" />
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

function spread(dots: ReturnType<typeof logoFrame>) {
  const xs = dots.map((d) => d.x);
  const ys = dots.map((d) => d.y);
  return { w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
}

describe("baked artwork", () => {
  it("keeps the playground's 244 points as baked: xyz per dot and one edge value each", () => {
    expect(POINTS.n).toBe(244);
    expect(POINTS.p).toHaveLength(732);
    expect(POINTS.e).toHaveLength(244);
    // First and last values of the pasted arrays, at Float32 precision.
    expect([...POINTS.p.slice(0, 3)]).toEqual([...Float32Array.from([0.16, 0.777, 0.06])]);
    expect([...POINTS.p.slice(-3)]).toEqual([...Float32Array.from([0.098, -0.754, 0.042])]);
    expect([...POINTS.e.slice(0, 3)]).toEqual([...Float32Array.from([0.031, 0.062, 0.031])]);
    expect(POINTS.e[243]).toBe(Math.fround(0.015));
  });
});

describe("modes", () => {
  // Mid-dwell: each mode is in its own form, before any morph.
  const FORM_AT = 2;

  it("keeps every dot of the mark inside the canvas and opaque when assembled, in every mode", () => {
    for (const mode of ACTIVITY_LOGO_MODES) {
      const mark = logoFrame(20, ASSEMBLED_AT, mode);
      expect(mark).toHaveLength(244);
      expect(mark.every((d) => d.a > 0.99)).toBe(true);
      // The whole mark, dot radius included, stays inside the 20px canvas.
      expect(mark.every((d) => d.x - d.r >= 0 && d.x + d.r <= 20)).toBe(true);
      expect(mark.every((d) => d.y - d.r >= 0 && d.y + d.r <= 20)).toBe(true);
    }
  });

  it("gives each mode its own form while it dwells", () => {
    const forms = ACTIVITY_LOGO_MODES.map((mode) => logoFrame(96, FORM_AT, mode));
    // Draw positions differ between every pair of modes.
    for (let a = 0; a < forms.length; a++) {
      for (let b = a + 1; b < forms.length; b++) {
        const pa = forms[a].map((d) => `${d.x.toFixed(2)},${d.y.toFixed(2)}`).sort();
        const pb = forms[b].map((d) => `${d.x.toFixed(2)},${d.y.toFixed(2)}`).sort();
        expect(pa).not.toEqual(pb);
      }
    }
    // Waiting's stack of rings is taller than it is wide; the thinking sphere is round.
    const waiting = spread(forms[ACTIVITY_LOGO_MODES.indexOf("waiting")]);
    expect(waiting.h).toBeGreaterThan(waiting.w);
    const sphere = spread(forms[ACTIVITY_LOGO_MODES.indexOf("thinking")]);
    expect(sphere.h / sphere.w).toBeCloseTo(1, 0);
  });

  it("winds working's thread over the dwell, faint ahead of the head when small", () => {
    const opaque = (t: number, size: number) =>
      logoFrame(size, t, "working").filter((d) => d.a > 0.99).length;
    // Laid dots grow as the head winds on.
    expect(opaque(1, 96)).toBeLessThan(opaque(3.5, 96));
    // At 96px the thread ahead of the head is absent, as the playground draws it.
    expect(logoFrame(96, 0.2, "working").length).toBeLessThan(40);
    // At 20px it stays as a faint knot, so the slot is never empty.
    const small = logoFrame(20, 0.2, "working");
    expect(small.length).toBe(244);
    expect(Math.min(...small.map((d) => d.a))).toBeGreaterThan(0.15);
  });

  it("dims searching's sphere outside the lit meridian", () => {
    const dots = logoFrame(96, FORM_AT, "searching");
    const alphas = dots.map((d) => d.a);
    expect(Math.min(...alphas)).toBeCloseTo(0.4, 1);
    expect(Math.max(...alphas)).toBeGreaterThan(0.9);
  });
});

describe("small-mark legibility", () => {
  // Mid-dwell: the dots sit on the turning sphere, before any morph.
  const SPHERE_AT = 2;

  it("eases in below 48px and leaves large marks untouched", () => {
    expect(smallness(96)).toBe(0);
    expect(smallness(48)).toBe(0);
    expect(smallness(20)).toBeCloseTo(28 / 30);
    expect(smallness(18)).toBe(1);
    // At 96px the sphere keeps every dot fully opaque, as the playground tuning draws it.
    expect(logoFrame(96, SPHERE_AT).every((d) => d.a === 1)).toBe(true);
  });

  it("fades the sphere's back hemisphere at 20px so it does not read as a flat disc", () => {
    const dots = logoFrame(20, SPHERE_AT);
    expect(dots).toHaveLength(244);
    // Draw order is back to front.
    const back = dots.slice(0, 50);
    const front = dots.slice(-50);
    const mean = (ds: typeof dots) => ds.reduce((s, d) => s + d.a, 0) / ds.length;
    expect(mean(back)).toBeLessThan(0.5);
    expect(mean(front)).toBeGreaterThan(0.85);
    // Nearer dots ink closer to the full tint than at 96px, on both substrates.
    const nearest = (size: number) => {
      const dots = logoFrame(size, SPHERE_AT);
      return dots[dots.length - 1].white;
    };
    expect(nearest(20)).toBeLessThan(nearest(96));
  });

  it("keeps small dots fine: a modest radius floor, and the mark no longer a solid blot", () => {
    const mark = logoFrame(20, ASSEMBLED_AT);
    const radii = mark.map((d) => d.r);
    // Between the playground's 0.3px floor and the 0.5px PR #1952 used.
    expect(Math.min(...radii)).toBeGreaterThanOrEqual(0.34);
    expect(Math.max(...radii)).toBeLessThan(0.5);
    // Summed dot area over the mark's bounding box. PR #1952's 495 dots at 24px summed
    // to 1.2 (dots overlapping into a blot); the 244 dots at 20px stay near half.
    const { w, h } = spread(mark);
    const ink = mark.reduce((s, d) => s + Math.PI * d.r * d.r, 0);
    expect(ink / (w * h)).toBeLessThan(0.6);
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
