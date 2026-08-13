import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TaskArtifactDownloads } from "../TaskArtifactDownloads";

describe("TaskArtifactDownloads", () => {
  it("renders figure JSON and raw NetCDF download links", () => {
    render(
      <TaskArtifactDownloads
        jsonFigurePaths={["/data/figure.json"]}
        rawDataPaths={["/data/raw data.nc"]}
      />,
    );

    expect(screen.getByRole("link", { name: "Figure JSON" }).getAttribute("href")).toBe(
      "/api/executions/artifact?path=%2Fdata%2Ffigure.json",
    );
    expect(screen.getByRole("link", { name: "Raw data (.nc)" }).getAttribute("href")).toBe(
      "/api/executions/artifact?path=%2Fdata%2Fraw%20data.nc",
    );
  });

  it("renders nothing without artifacts", () => {
    const { container } = render(<TaskArtifactDownloads />);
    expect(container.innerHTML).toBe("");
  });
});
