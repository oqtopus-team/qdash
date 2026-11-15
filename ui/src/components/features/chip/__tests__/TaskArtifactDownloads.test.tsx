import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TaskArtifactDownloads, hasTaskArtifactDownloads } from "../TaskArtifactDownloads";

describe("TaskArtifactDownloads", () => {
  afterEach(cleanup);

  it("offers preview and direct download for figure and raw data", () => {
    render(
      <TaskArtifactDownloads
        jsonFigurePaths={["/data/figure.json"]}
        rawDataPaths={["/data/raw data.nc"]}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: /Figure JSON.*figure\.json.*Preview/,
      }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download figure.json" }).getAttribute("href")).toBe(
      "/api/executions/artifact?path=%2Fdata%2Ffigure.json",
    );
    expect(screen.getByRole("button", { name: /Raw data.*raw data\.nc.*Preview/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download raw data.nc" }).getAttribute("href")).toBe(
      "/api/executions/artifact?path=%2Fdata%2Fraw%20data.nc",
    );
    expect(screen.getByRole("link", { name: "Download all (.zip)" }).getAttribute("href")).toBe(
      "/api/executions/artifacts/archive?paths=%2Fdata%2Ffigure.json&paths=%2Fdata%2Fraw+data.nc",
    );
  });

  it("disables archive download with a clear message above the API limit", () => {
    render(
      <TaskArtifactDownloads
        rawDataPaths={Array.from({ length: 101 }, (_, index) => `/data/raw-${index}.nc`)}
      />,
    );

    expect(
      (
        screen.getByRole("button", {
          name: "Download all (.zip)",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(screen.getByText(/Download all supports up to 100 files/)).toBeTruthy();
  }, 15_000);

  it("includes figure images in the archive without duplicate paths", () => {
    render(
      <TaskArtifactDownloads
        imagePaths={["/data/fig.png", "/data/fig.png", "/data/fig_2.png"]}
        jsonFigurePaths={["/data/fig.json"]}
        rawDataPaths={["/data/raw.nc"]}
      />,
    );

    const href = screen.getByRole("link", { name: "Download all (.zip)" }).getAttribute("href");
    expect(new URLSearchParams(href!.split("?")[1]).getAll("paths")).toEqual([
      "/data/fig.png",
      "/data/fig_2.png",
      "/data/fig.json",
      "/data/raw.nc",
    ]);
    expect(screen.getByText("Includes 2 figure images")).toBeTruthy();
    // Images are only added to the archive; preview and per-file links stay unchanged.
    expect(screen.queryByRole("link", { name: "Download fig.png" })).toBeNull();
    expect(screen.getByRole("link", { name: "Download fig.json" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download raw.nc" })).toBeTruthy();
  });

  it("offers download all when one artifact is paired with an image", () => {
    render(
      <TaskArtifactDownloads imagePaths={["/data/fig.png"]} jsonFigurePaths={["/data/fig.json"]} />,
    );

    expect(screen.getByRole("link", { name: "Download all (.zip)" }).getAttribute("href")).toBe(
      "/api/executions/artifacts/archive?paths=%2Fdata%2Ffig.png&paths=%2Fdata%2Ffig.json",
    );
    expect(screen.getByText("Includes 1 figure image")).toBeTruthy();
  });

  it("offers only download all for image-only records with several images", () => {
    render(<TaskArtifactDownloads imagePaths={["/data/a.png", "/data/b.png"]} />);

    expect(screen.getByRole("link", { name: "Download all (.zip)" }).getAttribute("href")).toBe(
      "/api/executions/artifacts/archive?paths=%2Fdata%2Fa.png&paths=%2Fdata%2Fb.png",
    );
    expect(screen.queryByRole("button", { name: /Preview/ })).toBeNull();
  });

  it("renders nothing for a single image or duplicate image paths", () => {
    expect(hasTaskArtifactDownloads({ imagePaths: ["/data/a.png", "/data/a.png"] })).toBe(false);
    const { container } = render(<TaskArtifactDownloads imagePaths={["/data/a.png"]} />);
    expect(container.innerHTML).toBe("");
  });

  it("counts image paths toward the archive limit", () => {
    render(
      <TaskArtifactDownloads
        imagePaths={Array.from({ length: 51 }, (_, index) => `/data/fig-${index}.png`)}
        rawDataPaths={Array.from({ length: 50 }, (_, index) => `/data/raw-${index}.nc`)}
      />,
    );

    expect(
      (screen.getByRole("button", { name: "Download all (.zip)" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByText(/Download all supports up to 100 files/)).toBeTruthy();
  }, 15_000);

  it("keeps download all enabled at the limit after removing duplicates", () => {
    const imagePaths = Array.from({ length: 50 }, (_, index) => `/data/fig-${index}.png`);
    render(
      <TaskArtifactDownloads
        imagePaths={[...imagePaths, ...imagePaths.slice(0, 5)]}
        rawDataPaths={Array.from({ length: 50 }, (_, index) => `/data/raw-${index}.nc`)}
      />,
    );

    expect(screen.getByRole("link", { name: "Download all (.zip)" })).toBeTruthy();
  }, 15_000);

  it("renders nothing without artifacts", () => {
    const { container } = render(<TaskArtifactDownloads />);
    expect(container.innerHTML).toBe("");
  });
});
