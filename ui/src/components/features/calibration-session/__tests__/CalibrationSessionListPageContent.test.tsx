import axios from "axios";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CalibrationSessionListPageContent } from "@/components/features/calibration-session/CalibrationSessionListPageContent";

const state = vi.hoisted(() => ({
  linked: { status: "ready", projectId: "lab-a" } as Record<string, string>,
  response: null as null | Record<string, unknown>,
  isError: false,
  isLoading: false,
  calls: [] as Array<{ params: Record<string, unknown>; project: unknown; enabled: boolean }>,
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("@/components/features/agent-session/useLinkedProject", () => ({
  useLinkedProject: () => state.linked,
  projectRequest: (projectId: string) => ({ headers: { "X-Project-Id": projectId } }),
}));
vi.mock("@/client/calibration-session/calibration-session", () => ({
  getListCalibrationSessionsQueryKey: (params: unknown) => ["/calibration-sessions", params],
  useListCalibrationSessions: (
    params: Record<string, unknown>,
    options: {
      query: { enabled: boolean };
      request?: { headers?: Record<string, string>; paramsSerializer?: { indexes: null } };
    },
  ) => {
    if (params.status) {
      const uri = axios.getUri({
        url: "/calibration-sessions",
        params,
        paramsSerializer: options.request?.paramsSerializer,
      });
      expect(uri).toContain("status=closed");
      expect(uri).not.toContain("status%5B%5D");
    }
    state.calls.push({
      params,
      project: options.request?.headers?.["X-Project-Id"],
      enabled: options.query.enabled,
    });
    return {
      data: state.response ? { data: state.response } : undefined,
      isLoading: state.isLoading,
      isError: state.isError,
      error: null,
    };
  },
}));

const SESSION = {
  calibration_session_id: "cs-1",
  project_id: "lab-a",
  chip_id: "64Qv3",
  objective: "Bring up qubits 0 and 1",
  created_by: "alice",
  status: "open",
  created_at: "2026-11-23T00:00:00Z",
  updated_at: "2026-11-23T00:00:00Z",
};

/** The params of the latest list request. */
const lastParams = () => state.calls[state.calls.length - 1]?.params;

function renderPage(searchParams = "") {
  return render(
    <NuqsTestingAdapter searchParams={searchParams} hasMemory>
      <CalibrationSessionListPageContent />
    </NuqsTestingAdapter>,
  );
}

afterEach(cleanup);
beforeEach(() => {
  state.linked = { status: "ready", projectId: "lab-a" };
  state.response = { items: [SESSION], total: 1, skip: 0, has_more: false };
  state.isError = false;
  state.isLoading = false;
  state.calls = [];
});

describe("CalibrationSessionListPageContent", () => {
  it("lists objectives linked to their page in the project it was read from", () => {
    renderPage();
    expect(state.calls[0]).toEqual({
      params: { limit: 20, skip: 0 },
      project: "lab-a",
      enabled: true,
    });
    const link = screen.getByRole("link", { name: "Bring up qubits 0 and 1" });
    expect(link.getAttribute("href")).toBe("/calibration-sessions/cs-1?project=lab-a");
    const row = within(link.closest("li") as HTMLElement);
    expect(row.getByText("Open")).toBeTruthy();
    // The row names its creator and chip the way execution cards name theirs.
    expect(row.getByText("@alice")).toBeTruthy();
    expect(row.getByText("Chip 64Qv3")).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Pages" })).toBeNull();
  });

  it("filters by status, creator, and the chip the Execution page linked", () => {
    renderPage("chip=64Qv3");
    expect(lastParams()).toEqual({ limit: 20, skip: 0, chip_id: "64Qv3" });
    fireEvent.click(screen.getByRole("tab", { name: "Closed" }));
    expect(lastParams()).toMatchObject({ status: ["closed"], chip_id: "64Qv3" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Only mine" }));
    expect(lastParams()).toMatchObject({ mine: true });
    fireEvent.click(screen.getByRole("button", { name: "Show every chip" }));
    expect(lastParams()).not.toHaveProperty("chip_id");
  });

  it("filters by origin and marks the sessions QDash created for single runs", () => {
    state.response = {
      items: [{ ...SESSION, calibration_session_id: "cs-auto-1", origin: "automatic" }],
      total: 1,
      skip: 0,
      has_more: false,
    };
    renderPage();
    const row = screen.getByRole("link", { name: "Bring up qubits 0 and 1" }).closest("li");
    expect(within(row as HTMLElement).getByText("Automatic")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: "Origin" }), {
      target: { value: "automatic" },
    });
    expect(lastParams()).toMatchObject({ origin: ["automatic"] });
    fireEvent.change(screen.getByRole("combobox", { name: "Origin" }), {
      target: { value: "all" },
    });
    expect(lastParams()).not.toHaveProperty("origin");
  });

  it("pages with the server's has_more", () => {
    state.response = { items: [SESSION], total: 1, skip: 0, has_more: true };
    renderPage();
    const pages = screen.getByRole("navigation", { name: "Pages" });
    expect(within(pages).getByRole("button", { name: "Previous" }).hasAttribute("disabled")).toBe(
      true,
    );
    fireEvent.click(within(pages).getByRole("button", { name: "Next" }));
    expect(lastParams()).toMatchObject({ skip: 20 });
  });

  it("names the empty, failed, and inaccessible states without a request for another project", () => {
    state.response = { items: [], total: 0, skip: 0, has_more: false };
    renderPage();
    expect(screen.getByText("No calibration sessions")).toBeTruthy();
    cleanup();
    state.isError = true;
    state.response = null;
    renderPage();
    expect(screen.getByRole("alert").textContent).toContain("could not be loaded");
    cleanup();
    state.calls = [];
    state.linked = { status: "unavailable", projectId: "lab-z" };
    renderPage();
    expect(screen.getByRole("alert").textContent).toContain("project lab-z");
    expect(state.calls.every((call) => !call.enabled)).toBe(true);
    // The view switch does not pin a project the account cannot open.
    const views = screen.getByRole("navigation", { name: "Execution views" });
    expect(within(views).getByRole("link", { name: "Executions" }).getAttribute("href")).toBe(
      "/execution",
    );
  });

  it("is the Execution area's session view, switching to Executions on the same chip", () => {
    renderPage("chip=64Qv3&status=closed");
    expect(screen.getByRole("heading", { level: 1, name: "Execution" })).toBeTruthy();
    const views = screen.getByRole("navigation", { name: "Execution views" });
    const sessions = within(views).getByRole("link", { name: "Calibration sessions" });
    const executions = within(views).getByRole("link", { name: "Executions" });
    expect(sessions.getAttribute("aria-current")).toBe("page");
    expect(executions.getAttribute("aria-current")).toBeNull();
    // Only the chip and project travel; the session status filter means nothing to Executions.
    expect(executions.getAttribute("href")).toBe("/execution?chip=64Qv3&project=lab-a");
  });

  it("links each session page with the list's filters and page, so it can link back", () => {
    state.response = { items: [SESSION], total: 21, skip: 20, has_more: false };
    renderPage("chip=64Qv3&status=closed&origin=manual&mine=true&page=2");
    expect(screen.getByRole("link", { name: "Bring up qubits 0 and 1" }).getAttribute("href")).toBe(
      "/calibration-sessions/cs-1?project=lab-a&chip=64Qv3&status=closed&origin=manual&mine=true&page=2",
    );
  });

  it("reads a list URL with values it does not know as the unfiltered list", () => {
    renderPage("status=bogus&origin=nope&page=abc");
    expect(lastParams()).toEqual({ limit: 20, skip: 0 });
    expect(screen.getByRole("link", { name: "Bring up qubits 0 and 1" }).getAttribute("href")).toBe(
      "/calibration-sessions/cs-1?project=lab-a",
    );
  });
});
