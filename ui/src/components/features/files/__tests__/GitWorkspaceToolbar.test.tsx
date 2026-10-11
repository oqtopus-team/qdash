import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GitWorkspaceToolbar, PullRequestBanner } from "../GitWorkspaceToolbar";

afterEach(cleanup);

describe("GitWorkspaceToolbar", () => {
  it("shows the branch and commit and wires the pull and PR actions", () => {
    const onPull = vi.fn();
    const onPush = vi.fn();
    render(
      <GitWorkspaceToolbar
        status={{ is_git_repo: true, branch: "main", commit: "b4023c48", is_dirty: true }}
        onPull={onPull}
        onPush={onPush}
        isPulling={false}
        isPushing={false}
      />,
    );

    expect(screen.getByText("main")).toBeTruthy();
    expect(screen.getByText("b4023c48")).toBeTruthy();
    expect(screen.getByTitle("Saved changes not yet in a pull request")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /pull/i }));
    fireEvent.click(screen.getByRole("button", { name: /create pr/i }));
    expect(onPull).toHaveBeenCalledTimes(1);
    expect(onPush).toHaveBeenCalledTimes(1);
  });

  it("flags remote updates on the pull button and hides the chip outside a repo", () => {
    render(
      <GitWorkspaceToolbar
        status={{ is_git_repo: false }}
        onPull={() => {}}
        onPush={() => {}}
        isPulling={false}
        isPushing={false}
      />,
    );
    expect(screen.queryByText("@")).toBeNull();
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
    expect(screen.getByRole("button", { name: /pull/i }).className).toContain("btn-warning");
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
