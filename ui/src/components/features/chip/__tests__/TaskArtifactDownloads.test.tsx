import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TaskArtifactDownloads } from "../TaskArtifactDownloads";

describe("TaskArtifactDownloads", () => {
  it("offers preview and direct download for figure and raw data", () => {
    render(
      <TaskArtifactDownloads
        jsonFigurePaths={["/data/figure.json"]}
        rawDataPaths={["/data/raw data.nc"]}
      />,
    );

    expect(screen.getByRole("button", { name: /Figure JSON.*figure\.json.*Preview/ })).toBeTruthy();
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

  it("renders nothing without artifacts", () => {
    const { container } = render(<TaskArtifactDownloads />);
    expect(container.innerHTML).toBe("");
  });
});
