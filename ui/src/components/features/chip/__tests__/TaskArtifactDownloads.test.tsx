import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TaskArtifactDownloads } from "../TaskArtifactDownloads";

describe("TaskArtifactDownloads", () => {
  it("makes preview the primary raw data action", () => {
    render(
      <TaskArtifactDownloads
        jsonFigurePaths={["/data/figure.json"]}
        rawDataPaths={["/data/raw data.nc"]}
      />,
    );

    expect(screen.getByRole("link", { name: "Figure JSON" }).getAttribute("href")).toBe(
      "/api/executions/artifact?path=%2Fdata%2Ffigure.json",
    );
    expect(screen.getByRole("button", { name: /Raw data.*raw data\.nc.*Preview/ })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Raw data/ })).toBeNull();
  });

  it("renders nothing without artifacts", () => {
    const { container } = render(<TaskArtifactDownloads />);
    expect(container.innerHTML).toBe("");
  });
});
