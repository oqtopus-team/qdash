import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlobalCommandPalette } from "@/components/layout/GlobalCommandPalette";
import { AVAILABLE_THEMES } from "@/constants/themes";

const push = vi.fn();
const switchProject = vi.fn();
const setTheme = vi.fn();
const success = vi.fn();
const error = vi.fn();
const taskInfoRequests = vi.fn();
const openGeneralChat = vi.fn();
const mockPathname = vi.hoisted(() => vi.fn(() => "/inbox"));
const mockCanEdit = vi.hoisted(() => vi.fn(() => false));

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
    canEdit: mockCanEdit(),
    projectId: "project-1",
    projects: [
      { project_id: "project-1", name: "Current lab" },
      { project_id: "project-2", name: "Calibration lab" },
    ],
    switchProject,
  }),
}));

vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({ openGeneralChat }),
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
    mockCanEdit.mockReturnValue(false);
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

  it("copies the page link over HTTP when the Clipboard API is unavailable", async () => {
    vi.stubGlobal(
      "navigator",
      new Proxy(navigator, {
        get(target, property) {
          if (property === "clipboard") return undefined;
          return Reflect.get(target, property, target);
        },
      }),
    );
    let copiedValue: string | undefined;
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      writable: true,
      value: vi.fn(() => {
        copiedValue = (document.activeElement as HTMLTextAreaElement | null)?.value;
        return true;
      }),
    });

    try {
      render(<GlobalCommandPalette />);
      fireEvent.keyDown(window, { key: "k", metaKey: true });
      fireEvent.click(screen.getByRole("option", { name: "Copy current page link" }));
      await waitFor(() => expect(success).toHaveBeenCalledWith("Page link copied"));
      expect(copiedValue).toBe(window.location.href);
      expect(error).not.toHaveBeenCalled();
    } finally {
      Reflect.deleteProperty(document, "execCommand");
    }
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

    fireEvent.click(screen.getByRole("option", { name: "Overview" }));

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
  it("lists create actions first and focuses the search input", () => {
    mockCanEdit.mockReturnValue(true);
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });

    const input = screen.getByRole("combobox", { name: "QDash navigation" });
    expect(document.activeElement).toBe(input);
    const options = screen.getAllByRole("option");
    expect(options[0].textContent).toContain("Create new workflow");
    expect(options[1].textContent).toContain("Create new thread");
    expect(options[0].getAttribute("aria-selected")).toBe("true");
  });

  it("opens the new workflow editor without saving anything for an editor", () => {
    mockCanEdit.mockReturnValue(true);
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter", keyCode: 13 });

    expect(push).toHaveBeenCalledOnce();
    expect(push).toHaveBeenCalledWith("/workflow/new");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers a viewer only the thread action, since workflows need write access", () => {
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });

    expect(screen.queryByRole("option", { name: /Create new workflow/ })).toBeNull();
    const [first] = screen.getAllByRole("option");
    expect(first.textContent).toContain("Create new thread");
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter", keyCode: 13 });
    expect(push).toHaveBeenCalledWith("/forum/new");
  });

  it("keeps the forum list filters when creating a thread from the forum", () => {
    mockPathname.mockReturnValue("/forum");
    window.history.replaceState({}, "", "/forum?status=open&category=question");
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByRole("option", { name: /Create new thread/ }));

    expect(push).toHaveBeenCalledWith(
      `/forum/new?from=${encodeURIComponent("status=open&category=question")}`,
    );
  });

  it("moves through results with the arrow keys and runs the selection with Enter", async () => {
    mockCanEdit.mockReturnValue(true);
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = screen.getByRole("combobox");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    await waitFor(() =>
      expect(
        screen.getByRole("option", { name: /Create new thread/ }).getAttribute("aria-selected"),
      ).toBe("true"),
    );
    // The list loops: up from the first result reaches the last theme.
    fireEvent.keyDown(input, { key: "ArrowUp" });
    fireEvent.keyDown(input, { key: "ArrowUp" });
    const lastTheme = AVAILABLE_THEMES[AVAILABLE_THEMES.length - 1];
    await waitFor(() =>
      expect(
        screen
          .getByRole("option", { name: `Use ${lastTheme} theme` })
          .getAttribute("aria-selected"),
      ).toBe("true"),
    );
    fireEvent.keyDown(input, { key: "Enter", keyCode: 13 });
    expect(setTheme).toHaveBeenCalledWith(lastTheme);
  });

  it("closes with Escape and returns focus to the trigger", async () => {
    render(<GlobalCommandPalette />);
    const trigger = screen.getByRole("button", { name: "Open navigation search" });
    trigger.focus();
    fireEvent.click(trigger);
    const input = screen.getByRole("combobox");
    expect(document.activeElement).toBe(input);

    fireEvent.keyDown(input, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
    expect(push).not.toHaveBeenCalled();
  });

  it("returns focus to the element focused before the shortcut opened the palette", async () => {
    const field = document.createElement("input");
    document.body.appendChild(field);
    field.focus();
    render(<GlobalCommandPalette />);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(document.activeElement).toBe(screen.getByRole("combobox"));
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(field));
    field.remove();
  });

  it("opens the agent chat through the chat dock and closes the palette", () => {
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByRole("option", { name: "Open agent chat" }));

    expect(openGeneralChat).toHaveBeenCalledOnce();
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it.each(["agent", "chat", "copilot", "チャット", "エージェント"])(
    "finds the agent chat action by %s",
    async (query) => {
      render(<GlobalCommandPalette />);
      fireEvent.keyDown(window, { key: "k", metaKey: true });
      fireEvent.change(screen.getByRole("combobox"), { target: { value: query } });

      await waitFor(() =>
        expect(screen.queryByRole("option", { name: "Create new thread" })).toBeNull(),
      );
      fireEvent.click(screen.getByRole("option", { name: "Open agent chat" }));
      expect(openGeneralChat).toHaveBeenCalledOnce();
      expect(screen.queryByRole("dialog")).toBeNull();
    },
  );

  it("runs the agent chat action with Enter when it is the top search result", async () => {
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "copilot" } });

    await waitFor(() =>
      expect(
        screen.getByRole("option", { name: "Open agent chat" }).getAttribute("aria-selected"),
      ).toBe("true"),
    );
    fireEvent.keyDown(input, { key: "Enter", keyCode: 13 });
    expect(openGeneralChat).toHaveBeenCalledOnce();
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("omits the agent chat action on the chat page, where the chat sidebar is hidden", () => {
    mockPathname.mockReturnValue("/chat");
    render(<GlobalCommandPalette />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });

    expect(screen.queryByRole("option", { name: "Open agent chat" })).toBeNull();
    expect(screen.getByRole("option", { name: "Agent" })).toBeTruthy();
    expect(openGeneralChat).not.toHaveBeenCalled();
  });
});
