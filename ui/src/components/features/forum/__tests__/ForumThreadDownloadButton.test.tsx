import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ForumPostResponse } from "@/schemas";

import { ForumThreadDownloadButton } from "../ForumThreadDownloadButton";

const { buildForumThreadZipMock } = vi.hoisted(() => ({
  buildForumThreadZipMock: vi.fn(),
}));

vi.mock("@/lib/forum/exportThreadZip", () => ({
  buildForumThreadZip: buildForumThreadZipMock,
}));

const { toastErrorMock } = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { error: toastErrorMock },
}));

const post = {
  id: "post-1",
  project_id: "project-1",
  category: "discussion",
  username: "alice",
  title: "Readout error",
  content: "Root content",
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
} as ForumPostResponse;

const replies = [
  {
    id: "reply-1",
    project_id: "project-1",
    category: "discussion",
    username: "bob",
    content: "Reply content",
    parent_id: "post-1",
    created_at: "2024-01-02T00:00:00Z",
    updated_at: "2024-01-02T00:00:00Z",
  } as ForumPostResponse,
];

describe("ForumThreadDownloadButton", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    buildForumThreadZipMock.mockReset();
    toastErrorMock.mockReset();
  });

  it("builds the zip and triggers a download with the returned filename", async () => {
    const blob = new Blob(["zip-bytes"]);
    buildForumThreadZipMock.mockResolvedValue({
      filename: "forum-0042-readout-error.zip",
      blob,
    });

    const createObjectURLMock = vi.fn().mockReturnValue("blob:mock-url");
    const revokeObjectURLMock = vi.fn();
    globalThis.URL.createObjectURL = createObjectURLMock as unknown as typeof URL.createObjectURL;
    globalThis.URL.revokeObjectURL = revokeObjectURLMock as unknown as typeof URL.revokeObjectURL;

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<ForumThreadDownloadButton post={post} replies={replies} />);

    fireEvent.click(screen.getByRole("button", { name: "Download thread" }));

    await waitFor(() => {
      expect(buildForumThreadZipMock).toHaveBeenCalledWith(post, replies);
    });

    await waitFor(() => {
      expect(clickSpy).toHaveBeenCalledOnce();
    });

    expect(createObjectURLMock).toHaveBeenCalledWith(blob);
    expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:mock-url");
  });

  it("disables the button when the disabled prop is true", () => {
    render(<ForumThreadDownloadButton post={post} replies={replies} disabled />);

    expect(screen.getByRole("button", { name: "Download thread" })).toBeDisabled();
  });

  it("shows an error toast and re-enables the button when export fails", async () => {
    buildForumThreadZipMock.mockRejectedValue(new Error("export failed"));

    render(<ForumThreadDownloadButton post={post} replies={replies} />);

    const button = screen.getByRole("button", { name: "Download thread" });
    fireEvent.click(button);

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("Failed to export thread");
    });

    await waitFor(() => {
      expect(button).not.toBeDisabled();
    });
  });
});
