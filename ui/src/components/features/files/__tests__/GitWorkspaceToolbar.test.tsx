import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GitWorkspaceToolbar, PullRequestBanner } from "../GitWorkspaceToolbar";

afterEach(cleanup);

describe("GitWorkspaceToolbar", () => {
  it("shows the branch and commit, pulls from the repository menu, and creates a PR", async () => {
    const onPull = vi.fn();
    const onPush = vi.fn();
    render(
      <GitWorkspaceToolbar
        status={{ is_git_repo: true, branch: "main", commit: "b4023c48", is_dirty: true }}
        onPull={onPull}
        onPush={onPush}
        isPulling={false}
        isPushing={false}
        menuItems={<div role="menuitem">Download as ZIP</div>}
      />,
    );

    const trigger = screen.getByRole("button", { name: /repository menu/i });
    expect(trigger.textContent).toContain("main");
    expect(trigger.textContent).toContain("b4023c48");
    expect(screen.getByLabelText("Saved changes not yet in a pull request")).toBeTruthy();

    fireEvent.pointerDown(trigger);
    fireEvent.click(await screen.findByRole("menuitem", { name: /pull latest/i }));
    expect(onPull).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Download as ZIP")).toBeNull(); // menu closed after the pull

    fireEvent.click(screen.getByRole("button", { name: /create pr/i }));
    expect(onPush).toHaveBeenCalledTimes(1);
  });

  it("flags remote updates on the trigger and says when nothing is cloned", async () => {
    render(
      <GitWorkspaceToolbar
        status={{ is_git_repo: false }}
        onPull={() => {}}
        onPush={() => {}}
        isPulling={false}
        isPushing={false}
      />,
    );
    expect(screen.getByRole("button", { name: /repository menu/i }).textContent).toContain(
      "No repository",
    );
    cleanup();

    render(
      <GitWorkspaceToolbar
        status={{ is_git_repo: true, branch: "main", commit: "1", has_remote_updates: true }}
        onPull={() => {}}
        onPush={() => {}}
        isPulling={false}
        isPushing={false}
      />,
    );
    const trigger = screen.getByRole("button", { name: /repository menu/i });
    expect(screen.getByTitle("Remote has new changes")).toBeTruthy();
    fireEvent.pointerDown(trigger);
    expect((await screen.findByRole("menuitem", { name: /pull latest/i })).textContent).toContain(
      "new",
    );
  });
});

describe("PullRequestBanner", () => {
  it("links to the created pull request and can be dismissed", () => {
    const onDismiss = vi.fn();
    render(
      <PullRequestBanner
        pr={{
          pr_url: "https://github.com/org/repo/pull/7",
          pr_number: 7,
          branch: "knowledge-update/x",
        }}
        onDismiss={onDismiss}
      />,
    );
    expect(screen.getByRole("link", { name: /open pr/i }).getAttribute("href")).toBe(
      "https://github.com/org/repo/pull/7",
    );
    fireEvent.click(screen.getByRole("button", { name: "✕" }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it("renders nothing without a pull request", () => {
    const { container } = render(<PullRequestBanner pr={null} onDismiss={() => {}} />);
    expect(container.innerHTML).toBe("");
  });
});
