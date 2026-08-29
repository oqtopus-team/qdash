import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionHistoryModalContent } from "@/components/features/task-history/ExecutionHistoryModalContent";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderContent(props?: Partial<React.ComponentProps<typeof ExecutionHistoryModalContent>>) {
  const onMobileTabChange = props?.onMobileTabChange ?? vi.fn();

  const utils = render(
    <ExecutionHistoryModalContent
      mobileTab="history"
      onMobileTabChange={onMobileTabChange}
      history={<div>History Content</div>}
      tasks={<div>Tasks Content</div>}
      details={<div>Details Content</div>}
      {...props}
    />,
  );

  return { ...utils, onMobileTabChange };
}

function getMobilePanel(container: HTMLElement) {
  return container.querySelector(".lg\\:hidden.flex-1");
}

function getDesktopPanel(container: HTMLElement) {
  return container.querySelector(".hidden.lg\\:flex");
}

describe("ExecutionHistoryModalContent", () => {
  it("renders only the selected tab on mobile", () => {
    const { container } = renderContent({ mobileTab: "details" });

    const mobilePanel = getMobilePanel(container);
    expect(mobilePanel).toBeTruthy();
    expect(mobilePanel?.textContent).toContain("Details Content");
    expect(mobilePanel?.textContent).not.toContain("History Content");
    expect(mobilePanel?.textContent).not.toContain("Tasks Content");
  });

  it("keeps the mobile tab panel scrollable", () => {
    const { container } = renderContent();

    const mobilePanel = getMobilePanel(container);
    expect(mobilePanel?.className).toContain("overflow-y-auto");
    expect(mobilePanel?.className).not.toContain("overflow-hidden");
  });

  it("switches tabs on click", () => {
    const onMobileTabChange = vi.fn();
    renderContent({ onMobileTabChange });

    fireEvent.click(screen.getByRole("button", { name: "History" }));
    expect(onMobileTabChange).toHaveBeenCalledWith("history");

    fireEvent.click(screen.getByRole("button", { name: "Tasks" }));
    expect(onMobileTabChange).toHaveBeenCalledWith("tasks");

    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(onMobileTabChange).toHaveBeenCalledWith("details");
  });

  it("renders all three panes on desktop", () => {
    const { container } = renderContent();

    const desktopPanel = getDesktopPanel(container);
    expect(desktopPanel).toBeTruthy();
    expect(desktopPanel?.textContent).toContain("History Content");
    expect(desktopPanel?.textContent).toContain("Tasks Content");
    expect(desktopPanel?.textContent).toContain("Details Content");
  });

  it("renders topContent when provided", () => {
    const { rerender } = renderContent({ topContent: <div>Top Content</div> });

    expect(screen.getByText("Top Content")).toBeTruthy();

    rerender(
      <ExecutionHistoryModalContent
        mobileTab="history"
        onMobileTabChange={vi.fn()}
        history={<div>History Content</div>}
        tasks={<div>Tasks Content</div>}
        details={<div>Details Content</div>}
      />,
    );

    expect(screen.queryByText("Top Content")).toBeNull();
  });
});
