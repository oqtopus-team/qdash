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
