import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";

vi.mock("theme-change", () => ({
  themeChange: vi.fn(),
}));

function ThemeValue() {
  const { theme } = useTheme();
  return <span>{theme}</span>;
}

describe("ThemeProvider", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    vi.unstubAllEnvs();
  });

  it("uses NEXT_PUBLIC_DEFAULT_THEME when no preference is saved", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEFAULT_THEME", "dark");

    render(
      <ThemeProvider>
        <ThemeValue />
      </ThemeProvider>,
    );

    await waitFor(() => expect(screen.getByText("dark")).toBeTruthy());
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("prefers a saved theme over the configured default", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEFAULT_THEME", "light");
    localStorage.setItem("theme", "synthwave");

    render(
      <ThemeProvider>
        <ThemeValue />
      </ThemeProvider>,
    );

    await waitFor(() => expect(screen.getByText("synthwave")).toBeTruthy());
    expect(document.documentElement.getAttribute("data-theme")).toBe("synthwave");
    expect(localStorage.getItem("theme")).toBe("synthwave");
  });

  it("falls back to light when the configured default is invalid", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEFAULT_THEME", "unknown");

    render(
      <ThemeProvider>
        <ThemeValue />
      </ThemeProvider>,
    );

    await waitFor(() => expect(screen.getByText("light")).toBeTruthy());
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
