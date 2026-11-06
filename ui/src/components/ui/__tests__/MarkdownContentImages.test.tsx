import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarkdownContent, type MarkdownImageLoader } from "../MarkdownContent";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("MarkdownContent images", () => {
  afterEach(() => cleanup());

  it("loads a relative image through the loader and shows it as a blob URL", async () => {
    const createObjectURL = vi.fn(() => "blob:rabi");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const loader: MarkdownImageLoader = {
      cacheKey: "knowledge",
      resolve: (src) => (src.startsWith("./") ? `CheckRabi/${src.slice(2)}` : null),
      load: vi.fn(async () => new Blob(["png"], { type: "image/png" })),
    };

    renderWithClient(
      <MarkdownContent
        content={"![Rabi plot](./expected.png)\n\n![remote](https://example.com/a.png)"}
        imageLoader={loader}
      />,
    );

    expect(await screen.findByAltText("Rabi plot")).toHaveAttribute("src", "blob:rabi");
    expect(loader.load).toHaveBeenCalledWith("CheckRabi/expected.png");
    expect(screen.getByAltText("remote")).toHaveAttribute("src", "https://example.com/a.png");
  });

  it("says so when the image cannot be loaded", async () => {
    const loader: MarkdownImageLoader = {
      cacheKey: "knowledge",
      resolve: () => "CheckRabi/missing.png",
      load: vi.fn(async () => {
        throw new Error("404");
      }),
    };

    renderWithClient(
      <MarkdownContent content="![Missing plot](./missing.png)" imageLoader={loader} />,
    );

    expect(await screen.findByText(/Missing plot \(not found\)/)).toBeInTheDocument();
  });
});
