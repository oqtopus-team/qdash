import { describe, expect, it } from "vitest";

import {
  getMobileTabs,
  getNavigationSections,
  isMobileTabActive,
  isPathWithin,
  withoutMobileTabs,
} from "@/components/layout/navigation";

const editor = getNavigationSections({ canEdit: true, isAdmin: false });
const viewer = getNavigationSections({ canEdit: false, isAdmin: false });

function tabFor(href: string) {
  const tab = getMobileTabs(editor).find((candidate) => candidate.item.href === href);
  if (!tab) throw new Error(`Expected a mobile tab for ${href}`);
  return tab;
}

describe("isPathWithin", () => {
  it("matches the base route and routes nested under it", () => {
    expect(isPathWithin("/workflow", "/workflow")).toBe(true);
    expect(isPathWithin("/workflow/new", "/workflow")).toBe(true);
  });

  it("does not match a sibling route that shares a prefix", () => {
    expect(isPathWithin("/workflows", "/workflow")).toBe(false);
    expect(isPathWithin("/dashboard-old", "/dashboard")).toBe(false);
  });
});

describe("getMobileTabs", () => {
  it("returns Dashboard, Workflow, Execution, and AI Chat in order for project editors", () => {
    const tabs = getMobileTabs(editor);

    expect(tabs.map((tab) => tab.item.label)).toEqual([
      "Dashboard",
      "Workflow",
      "Execution",
      "AI Chat",
    ]);
    expect(tabs.map((tab) => tab.item.href)).toEqual([
      "/dashboard",
      "/workflow",
      "/execution",
      "/chat",
    ]);
  });

  it("drops Workflow when the sidebar hides it from viewers", () => {
    expect(getMobileTabs(viewer).map((tab) => tab.item.label)).toEqual([
      "Dashboard",
      "Execution",
      "AI Chat",
    ]);
  });
});

describe("isMobileTabActive", () => {
  it.each([
    ["/dashboard", "/dashboard"],
    ["/workflow", "/workflow"],
    ["/workflow/new", "/workflow"],
    ["/workflow/my-flow", "/workflow"],
    ["/execution", "/execution"],
    ["/execution/chip-1/exec-1", "/execution"],
    ["/executions/exec-1", "/execution"],
    ["/chat", "/chat"],
    ["/chat/session-1", "/chat"],
  ])("marks %s as belonging to the %s tab", (pathname, href) => {
    const active = getMobileTabs(editor).filter((tab) => isMobileTabActive(tab, pathname));

    expect(active.map((tab) => tab.item.href)).toEqual([href]);
  });

  it.each(["/home", "/metrics", "/task-results/abc", "/workflows", "/chats", "/settings"])(
    "leaves every tab inactive on %s",
    (pathname) => {
      for (const href of ["/dashboard", "/workflow", "/execution", "/chat"]) {
        expect(isMobileTabActive(tabFor(href), pathname)).toBe(false);
      }
    },
  );
});

describe("withoutMobileTabs", () => {
  it("keeps every other destination and section in sidebar order", () => {
    const sections = withoutMobileTabs(editor);
    const hrefs = sections.flatMap((section) => section.items.map((item) => item.href));

    expect(sections.map((section) => section.label)).toEqual(editor.map((s) => s.label));
    expect(hrefs).not.toContain("/dashboard");
    expect(hrefs).not.toContain("/workflow");
    expect(hrefs).not.toContain("/execution");
    expect(hrefs).not.toContain("/chat");
    expect(hrefs).toEqual(
      editor
        .flatMap((section) => section.items.map((item) => item.href))
        .filter((href) => !["/dashboard", "/workflow", "/execution", "/chat"].includes(href)),
    );
  });

  it("preserves item visibility flags", () => {
    const admin = withoutMobileTabs(viewer)
      .flatMap((section) => section.items)
      .find((item) => item.href === "/admin");

    expect(admin?.visible).toBe(false);
  });
});
