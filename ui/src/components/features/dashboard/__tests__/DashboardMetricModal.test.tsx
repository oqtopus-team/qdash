import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DashboardMetricModal } from "@/components/features/dashboard/DashboardMetricModal";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/components/features/metrics/QubitMetricHistoryModal", () => ({
  QubitMetricHistoryModal: () => <div data-testid="qubit-history" />,
}));

vi.mock("@/components/features/metrics/CouplingMetricHistoryModal", () => ({
  CouplingMetricHistoryModal: () => <div data-testid="coupling-history" />,
}));

vi.mock("../MetricNotePanel", () => ({
  MetricNotePanel: () => <div data-testid="note-panel" />,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderModal(overrides?: Partial<React.ComponentProps<typeof DashboardMetricModal>>) {
  const onClose = overrides?.onClose ?? vi.fn();

  const result = render(
    <DashboardMetricModal
      chipId="chip-1"
      targetId="72"
      metricKey="t1"
      metricTitle="T1"
      metricUnit="us"
      onClose={onClose}
      {...overrides}
    />,
  );

  return { onClose, ...result };
}

describe("DashboardMetricModal", () => {
  it("scrolls the body as a single column on mobile", () => {
    renderModal();

    const body = screen.getByTestId("note-panel").parentElement?.parentElement;

    expect(body).not.toBeNull();
    expect(body?.className).toContain("overflow-y-auto");
    expect(body?.className).toContain("lg:overflow-hidden");
  });

  it("lets the history pane grow to its content on mobile", () => {
    renderModal();

    const historyPane = screen.getByTestId("qubit-history").parentElement;

    expect(historyPane).not.toBeNull();
    expect(historyPane?.className).toContain("flex-none");
    expect(historyPane?.className).toContain("lg:overflow-auto");
    expect(historyPane?.className).not.toContain("min-h-0 min-w-0 overflow-auto");
  });

  it("renders the coupling history for a coupling target", () => {
    renderModal({ targetId: "72-73" });

    expect(screen.getByTestId("coupling-history")).toBeTruthy();
    expect(screen.queryByTestId("qubit-history")).toBeNull();
  });

  it("renders the qubit history for a qubit target", () => {
    renderModal({ targetId: "72" });

    expect(screen.getByTestId("qubit-history")).toBeTruthy();
    expect(screen.queryByTestId("coupling-history")).toBeNull();
  });

  it("hides the lineage link for a coupling target", () => {
    const { unmount } = renderModal({ targetId: "72-73" });

    expect(screen.queryByText("Lineage")).toBeNull();
    expect(screen.queryByText("Details")).toBeNull();

    unmount();

    renderModal({ targetId: "72" });

    expect(screen.getByText("Lineage")).toBeTruthy();
    expect(screen.getByText("Details")).toBeTruthy();
  });

  it("calls onClose from the header and footer buttons", () => {
    const { onClose } = renderModal();

    const closeButtons = screen.getAllByRole("button", { name: "Close" });
    expect(closeButtons).toHaveLength(2);

    fireEvent.click(closeButtons[0]);
    fireEvent.click(closeButtons[1]);

    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
