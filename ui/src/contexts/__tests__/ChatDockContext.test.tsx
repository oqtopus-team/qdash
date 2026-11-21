import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChatDockProvider, useChatDock } from "../ChatDockContext";
import type { EditProposal, PageContext } from "@/types/copilotChat";

vi.mock("next/navigation", () => ({ usePathname: () => "/workflow/t1" }));
vi.mock("../CopilotChatSessionContext", () => ({
  useCopilotChatSessionContext: () => ({ activeSession: null }),
}));
afterEach(cleanup);

it("checks the registered editor's current target at application time", () => {
  const { result } = renderHook(() => useChatDock(), { wrapper: ChatDockProvider });
  const edit: EditProposal = {
    flowName: "t1",
    chipId: "chip1",
    pagePath: "/workflow/t1",
    code: "new",
    summary: "Update",
  };
  let page: PageContext = {
    title: "Workflow editor: t1",
    path: edit.pagePath,
    flow: { name: "t1", chipId: "chip1", code: "old", dirty: true },
  };
  const applyCode = vi.fn();
  let unregister: () => void;
  act(() => {
    unregister = result.current.registerPage({ current: () => page, applyCode });
  });
  const apply = result.current.applyCode;
  expect(apply(edit)).toBe(true);
  expect(applyCode).toHaveBeenLastCalledWith("new");
  applyCode.mockClear();

  // The provider reads an editor ref: switching chip need not rerender the chat.
  page = { ...page, flow: { ...page.flow!, chipId: "chip2" } };
  expect(apply(edit)).toBe(false);
  expect(applyCode).not.toHaveBeenCalled();
  act(() => unregister());
  expect(apply(edit)).toBe(false);
});

it("reports editor code for a metric script page and applies a script proposal there", () => {
  const { result } = renderHook(() => useChatDock(), { wrapper: ChatDockProvider });
  const page: PageContext = {
    title: "Metric script: ZX90",
    path: "/workflow/t1",
    metricScript: { scriptId: "ms_1", name: "ZX90", code: "old", dirty: false },
  };
  const applyCode = vi.fn();
  act(() => {
    result.current.registerPage({ current: () => page, applyCode });
  });

  expect(result.current.pageSummary()).toEqual({
    path: "/workflow/t1",
    title: "Metric script: ZX90",
    withEditorCode: true,
  });
  const edit: EditProposal = {
    summary: "Update",
    code: "new",
    target: "metric_script",
    flowName: "ZX90",
    chipId: null,
    scriptId: "ms_1",
    pagePath: "/workflow/t1",
  };
  expect(result.current.applyCode(edit)).toBe(true);
  expect(applyCode).toHaveBeenLastCalledWith("new");
  expect(result.current.applyCode({ ...edit, scriptId: "ms_2" })).toBe(false);
});

it("summarizes a dashboard draft with its suggestions and reports a refused draft", () => {
  const { result } = renderHook(() => useChatDock(), { wrapper: ChatDockProvider });
  const page: PageContext = {
    title: "New dashboard",
    path: "/workflow/t1",
    dashboard: { name: "", code: "{}" },
  };
  const applyCode = vi.fn(() => false);
  act(() => {
    result.current.registerPage({
      current: () => page,
      applyCode,
      suggestions: () => ["Show T1 per qubit"],
    });
  });

  const summary = result.current.pageSummary();
  expect(summary).toEqual({
    path: "/workflow/t1",
    title: "New dashboard",
    withEditorCode: true,
    editorKind: "dashboard",
    suggestions: ["Show T1 per qubit"],
  });
  // Unchanged pages keep the same summary object, so the chat does not rerender.
  expect(result.current.pageSummary()).toBe(summary);
  const edit: EditProposal = {
    summary: "Add a panel",
    code: "{bad",
    target: "dashboard",
    flowName: "",
    chipId: null,
    dashboardId: null,
    pagePath: "/workflow/t1",
  };
  expect(result.current.applyCode(edit)).toBe(false);
  expect(applyCode).toHaveBeenLastCalledWith("{bad");
  applyCode.mockReturnValue(true as never);
  expect(result.current.applyCode(edit)).toBe(true);
});
