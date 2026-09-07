import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlobalCommandPalette } from "@/components/layout/GlobalCommandPalette";

const push = vi.fn();
const switchProject = vi.fn();
const setTheme = vi.fn();
const success = vi.fn();
const error = vi.fn();
const taskInfoRequests = vi.fn();
const mockPathname = vi.hoisted(() => vi.fn(() => "/inbox"));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => mockPathname(),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({
    qubitMetrics: [{ key: "t1", title: "T1" }],
    couplingMetrics: [{ key: "zx90_gate_fidelity", title: "ZX90 Gate Fidelity" }],
  }),
}));

vi.mock("@/client/task-file/task-file", () => ({
  useGetTaskFileSettings: () => ({ data: { data: { default_backend: "qubex" } } }),
  useListTaskInfo: (params: { backend: string }) => {
    taskInfoRequests(params);
    return {
      data: {
        data: {
          tasks: [
            {
              name: "CheckRabi",
              task_type: "qubit",
              file_path: "one_qubit/check_rabi.py",
            },
          ],
        },
      },
    };
  },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { system_role: "user" } }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    canEdit: false,
    projectId: "project-1",
    projects: [
      { project_id: "project-1", name: "Current lab" },
      { project_id: "project-2", name: "Calibration lab" },
    ],
    switchProject,
  }),
}));

vi.mock("@/contexts/ThemeContext", () => ({
  useTheme: () => ({ theme: "light", setTheme }),
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success, error }),
}));

function mockClipboard(writeText: ReturnType<typeof vi.fn>) {
  vi.stubGlobal(
    "navigator",
    new Proxy(navigator, {
      get(target, property) {
        if (property === "clipboard") return { writeText };
        return Reflect.get(target, property, target);
      },
    }),
  );
}

describe("GlobalCommandPalette", () => {
  afterEach(() => {
    cleanup();
    push.mockReset();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    mockPathname.mockReturnValue("/inbox");
    window.history.replaceState({}, "", "/inbox");
  });

  it("finds a project by name and switches using Enter", async () => {
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "Calibration lab" } });
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));
    fireEvent.keyDown(input, { key: "Enter", keyCode: 13 });
    expect(switchProject).toHaveBeenCalledWith("project-2");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });

  it("marks the current project unavailable and changes theme through the existing provider", () => {
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(
      screen.getByText("Current lab").closest("[cmdk-item]")?.getAttribute("aria-disabled"),
    ).toBe("true");
    fireEvent.click(screen.getByRole("option", { name: "Use dark theme" }));
    expect(setTheme).toHaveBeenCalledWith("dark");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("copies the full page link including filters and confirms completion", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockClipboard(writeText);
    window.history.replaceState({}, "", "/metrics?project=project-1&chip=chip-1#results");
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByRole("option", { name: "Copy current page link" }));
    await waitFor(() => expect(success).toHaveBeenCalledWith("Page link copied"));
    expect(writeText).toHaveBeenCalledWith(window.location.href);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the palette open and reports a clipboard failure", async () => {
    mockClipboard(vi.fn().mockRejectedValue(new Error("Permission denied")));
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByRole("option", { name: "Copy current page link" }));
    await waitFor(() => expect(error).toHaveBeenCalledOnce());
    expect(success).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("ignores shortcut repeats and IME composition", () => {
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true, isComposing: true });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.keyDown(window, { key: "k", ctrlKey: true, repeat: true });
    expect(screen.getByRole("dialog")).toBeTruthy();
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

  it("opens the selected task workbench using the configured default backend", () => {
    mockPathname.mockReturnValue("/tasks");
    window.history.replaceState({}, "", "/tasks");

    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByRole("option", { name: /CheckRabi.*qubit/i }));

    expect(push).toHaveBeenCalledWith("/tasks?backend=qubex&task=CheckRabi");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("uses the active URL backend and preserves project and chip while clearing old execution state", () => {
    mockPathname.mockReturnValue("/tasks");
    window.history.replaceState(
      {},
      "",
      "/tasks?project=project-1&chip=chip-1&backend=custom&task=CheckT1&execution=old-run&executionChip=old-chip&executionTarget=0",
    );
    render(<GlobalCommandPalette />);
    expect(taskInfoRequests).toHaveBeenLastCalledWith({ backend: "custom" });
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByRole("option", { name: /CheckRabi.*qubit/i }));
    expect(push).toHaveBeenCalledWith(
      "/tasks?project=project-1&chip=chip-1&backend=custom&task=CheckRabi",
    );
  });

  it("updates task commands when the backend in the URL changes", () => {
    mockPathname.mockReturnValue("/tasks");
    window.history.replaceState({}, "", "/tasks?backend=first");
    const { rerender } = render(<GlobalCommandPalette />);
    expect(taskInfoRequests).toHaveBeenLastCalledWith({ backend: "first" });
    window.history.replaceState({}, "", "/tasks?backend=second");
    rerender(<GlobalCommandPalette />);
    expect(taskInfoRequests).toHaveBeenLastCalledWith({ backend: "second" });
  });
});
