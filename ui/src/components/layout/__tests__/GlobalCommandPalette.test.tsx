import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlobalCommandPalette } from "@/components/layout/GlobalCommandPalette";

const push = vi.fn();
const mockPathname = vi.hoisted(() => vi.fn(() => "/inbox"));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => mockPathname(),
}));

vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({
    qubitMetrics: [{ key: "t1", title: "T1" }],
    couplingMetrics: [{ key: "zx90_gate_fidelity", title: "ZX90 Gate Fidelity" }],
  }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { system_role: "user" } }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: false }),
}));

describe("GlobalCommandPalette", () => {
  afterEach(() => {
    cleanup();
    push.mockReset();
    mockPathname.mockReturnValue("/inbox");
  });

  it("opens with the platform shortcut and navigates to a selected page", () => {
    render(<GlobalCommandPalette />);

    fireEvent.keyDown(window, { key: "k", metaKey: true });

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "QDash navigation" })).toBeTruthy();

    fireEvent.click(screen.getByRole("option", { name: "Dashboard" }));

    expect(push).toHaveBeenCalledWith("/dashboard");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("hides pages unavailable to the current user", () => {
    render(<GlobalCommandPalette />);
    fireEvent.click(screen.getByRole("button", { name: "Open navigation search" }));

    expect(screen.queryByRole("option", { name: "Workflow" })).toBeNull();
    expect(screen.queryByRole("option", { name: "Admin" })).toBeNull();
    expect(screen.getByRole("option", { name: "Settings" })).toBeTruthy();
  });

  it("shows dashboard metrics and jumps to the selected metric", async () => {
    mockPathname.mockReturnValue("/dashboard");
    const target = document.createElement("div");
    target.id = "dashboard-coupling-metric-zx90_gate_fidelity";
    const scrollIntoView = vi.fn();
    Object.defineProperty(target, "scrollIntoView", { value: scrollIntoView });
    document.body.appendChild(target);

    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByRole("option", { name: /ZX90 Gate Fidelity.*Coupling/ }));

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    target.remove();
  });

  it("switches the selected metric on the metrics page", () => {
    mockPathname.mockReturnValue("/metrics");
    window.history.replaceState({}, "", "/metrics?project=project-1&chip=chip-1");

    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByRole("option", { name: /ZX90 Gate Fidelity.*Coupling/ }));

    expect(push).toHaveBeenCalledWith(
      "/metrics?project=project-1&chip=chip-1&type=coupling&metric=zx90_gate_fidelity",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
