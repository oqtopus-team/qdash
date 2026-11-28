import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GridLoadingPanel, GridTaskRequestAlerts } from "../GridTaskStatus";

afterEach(() => cleanup());

describe("GridTaskRequestAlerts", () => {
  it("names the task and date while refreshing", () => {
    render(
      <GridTaskRequestAlerts
        selectedTask="CheckRabi"
        selectedDate="20261110"
        isRefreshing
        isError={false}
        error={null}
      />,
    );

    expect(screen.getByText("Loading CheckRabi data for 20261110")).not.toBeNull();
  });

  it("names an open range and the API detail on failure", () => {
    render(
      <GridTaskRequestAlerts
        selectedTask="CheckRabi"
        selectedDate="latest"
        startAt="2026-11-01"
        isRefreshing={false}
        isError
        error={{ response: { data: { detail: "No chip" } } }}
      />,
    );

    expect(
      screen.getByText("Failed to load CheckRabi data for 2026-11-01 - ...: No chip"),
    ).not.toBeNull();
  });

  it("joins validation details and omits a missing detail", () => {
    const { rerender } = render(
      <GridTaskRequestAlerts
        selectedTask="T1"
        selectedDate="latest"
        isRefreshing={false}
        isError
        error={{ response: { data: { detail: [{ loc: ["task"] }] } } }}
      />,
    );
    expect(screen.getByText('Failed to load T1 data for latest: {"loc":["task"]}')).not.toBeNull();

    rerender(
      <GridTaskRequestAlerts
        selectedTask="T1"
        selectedDate="latest"
        isRefreshing={false}
        isError
        error={new Error("network")}
      />,
    );
    expect(screen.getByText("Failed to load T1 data for latest")).not.toBeNull();
  });
});

describe("GridLoadingPanel", () => {
  it("offers the fullscreen exit only in fullscreen", () => {
    const onExitFullscreen = vi.fn();
    const { rerender } = render(
      <GridLoadingPanel
        className="panel"
        isFullscreen={false}
        onExitFullscreen={onExitFullscreen}
      />,
    );
    expect(screen.queryByRole("button", { name: "Exit fullscreen" })).toBeNull();

    rerender(
      <GridLoadingPanel className="panel" isFullscreen onExitFullscreen={onExitFullscreen} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Exit fullscreen" }));
    expect(onExitFullscreen).toHaveBeenCalledTimes(1);
  });
});
