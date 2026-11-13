import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FileWorkspace } from "@/lib/fileWorkspace";

import { WorkspaceChangesView, changedPaths, gitStatusEntries } from "../WorkspaceChangesView";

vi.mock("next/dynamic", () => ({
  default: () => (props: { filename: string; newContent: string; oldContent: string }) => (
    <div data-testid="diff">
      {props.filename}: {props.oldContent} → {props.newContent}
    </div>
  ),
}));

afterEach(cleanup);

const status = {
  is_git_repo: true,
  commit: "abc12345",
  changed_files: ["a.yaml", "gone.yaml"],
  untracked_files: ["new.md"],
};

describe("git status helpers", () => {
  it("lists changed and untracked files once and decorates the tree", () => {
    expect(changedPaths(status)).toEqual(["a.yaml", "gone.yaml", "new.md"]);
    expect(gitStatusEntries(status)).toEqual([
      { path: "a.yaml", status: "modified" },
      { path: "gone.yaml", status: "modified" },
      { path: "new.md", status: "untracked" },
    ]);
    expect(changedPaths({ is_git_repo: false })).toEqual([]);
    expect(gitStatusEntries(undefined)).toEqual([]);
  });
});

describe("WorkspaceChangesView", () => {
  it("shows every saved change as a diff and marks files that are gone", async () => {
    const getContent = vi.fn(async (path: string) => {
      if (path === "gone.yaml") throw new Error("404");
      return {
        content: `${path} new`,
        base_content: path === "new.md" ? "" : `${path} old`,
        is_saved_change: true,
        path,
        name: path,
        size: 1,
        modified: "",
      };
    });
    const workspace = { key: "config", getContent } as unknown as FileWorkspace;
    const onOpenFile = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <WorkspaceChangesView workspace={workspace} status={status} onOpenFile={onOpenFile} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("a.yaml: a.yaml old → a.yaml new")).toBeTruthy();
    expect(await screen.findByText("new.md: → new.md new")).toBeTruthy();
    expect(await screen.findByText("deleted")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "a.yaml" }));
    expect(onOpenFile).toHaveBeenCalledWith("a.yaml");
  });

  it("explains an empty state", () => {
    const workspace = { key: "config", getContent: vi.fn() } as unknown as FileWorkspace;
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <WorkspaceChangesView
          workspace={workspace}
          status={{ is_git_repo: true, changed_files: [] }}
          onOpenFile={() => {}}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("No changes")).toBeTruthy();
  });
});
