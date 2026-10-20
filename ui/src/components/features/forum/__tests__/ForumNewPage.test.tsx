import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ForumNewPage } from "../ForumNewPage";

const mocks = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  push: vi.fn(),
  triggerAiReply: vi.fn(),
  invalidateQueries: vi.fn(),
  params: new URLSearchParams(),
  snapshot: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => mocks.params,
}));

vi.mock("next/dynamic", () => ({
  default: () =>
    /** Stand-in editor that reports changes and exposes the snapshot getter. */
    function MockEditor(props: {
      legacyMarkdown?: string;
      onChange: (blocks: Record<string, unknown>[], markdown: string) => void;
      snapshotRef?: { current: (() => Promise<unknown>) | null };
    }) {
      if (props.snapshotRef) props.snapshotRef.current = mocks.snapshot;
      return (
        <textarea
          aria-label="Content editor"
          defaultValue={props.legacyMarkdown}
          onChange={(event) => props.onChange([{ id: "b1" }], event.target.value)}
        />
      );
    },
}));

vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({ data: { data: { chips: [{ chip_id: "64Qv3" }] } } }),
}));
vi.mock("@/client/cooldown/cooldown", () => ({
  useListCooldowns: () => ({ data: undefined }),
}));
vi.mock("@/client/forum/forum", () => ({
  getListForumPostsQueryKey: () => ["forum-posts"],
  useCreateForumPost: () => ({
    mutateAsync: mocks.mutateAsync,
    isPending: false,
  }),
  useListForumCategories: () => ({ data: undefined }),
}));
vi.mock("@/client/projects/projects", () => ({
  useListProjectMembers: () => ({ data: undefined }),
}));
vi.mock("../ForumLabelSelector", () => ({ ForumLabelPicker: () => null }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { username: "alice" } }),
}));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "p1" }),
}));
vi.mock("@/hooks/useForumAiReply", () => ({
  useForumAiReply: () => ({ triggerAiReply: mocks.triggerAiReply }),
}));
vi.mock("@/hooks/useForumLabels", () => ({
  useForumLabels: () => ({ labels: [] }),
}));
vi.mock("@/hooks/useImageUpload", () => ({
  useImageUpload: () => ({ uploadImage: vi.fn() }),
}));

/** Clicks the Post button. */
function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Post" }));
}

describe("ForumNewPage", () => {
  beforeEach(() => {
    mocks.params = new URLSearchParams();
    mocks.snapshot.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    mocks.mutateAsync.mockReset();
    mocks.push.mockReset();
    mocks.triggerAiReply.mockReset();
    mocks.invalidateQueries.mockReset();
    mocks.snapshot.mockReset();
  });

  it("shows an inline error for an empty title and does not submit", async () => {
    render(<ForumNewPage />);
    fireEvent.change(screen.getByLabelText("Content editor"), {
      target: { value: "hello" },
    });
    submit();

    const error = await screen.findByText("Title is required");
    const input = screen.getByLabelText("Thread title");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe(error.id);
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("shows an error when the content is empty", async () => {
    render(<ForumNewPage />);
    fireEvent.change(screen.getByLabelText("Thread title"), {
      target: { value: "Title" },
    });
    submit();

    expect(await screen.findByText("Content is required")).toBeTruthy();
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("rejects whitespace-only content", async () => {
    render(<ForumNewPage />);
    fireEvent.change(screen.getByLabelText("Thread title"), { target: { value: "Title" } });
    fireEvent.change(screen.getByLabelText("Content editor"), {
      target: { value: "   " },
    });
    submit();

    expect(await screen.findByText("Content is required")).toBeTruthy();
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("does not submit when Enter is pressed in the title", async () => {
    mocks.params = new URLSearchParams({ title: "T", content: "C" });
    mocks.mutateAsync.mockResolvedValue({ data: { id: "post-5" } });
    render(<ForumNewPage />);
    fireEvent.keyDown(screen.getByLabelText("Thread title"), { key: "Enter" });

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("clears the category error once a valid category is chosen", async () => {
    mocks.params = new URLSearchParams({ title: "T", content: "C", category: "Bad" });
    render(<ForumNewPage />);
    submit();

    expect(await screen.findByText(/Category must be lowercase/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "qubit" } });
    await waitFor(() => expect(screen.queryByText(/Category must be lowercase/)).toBeNull());
  });

  it("rejects content longer than 8000 characters", async () => {
    render(<ForumNewPage />);
    fireEvent.change(screen.getByLabelText("Thread title"), {
      target: { value: "Title" },
    });
    fireEvent.change(screen.getByLabelText("Content editor"), {
      target: { value: "a".repeat(8001) },
    });
    submit();

    expect(await screen.findByText("Content must be 8000 characters or fewer")).toBeTruthy();
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("submits a normalized payload and redirects", async () => {
    mocks.params = new URLSearchParams({ from: "status=open" });
    mocks.mutateAsync.mockResolvedValue({ data: { id: "post-1" } });
    render(<ForumNewPage />);
    fireEvent.change(screen.getByLabelText("Thread title"), {
      target: { value: "  Hello  " },
    });
    fireEvent.change(screen.getByLabelText("Content editor"), {
      target: { value: "  body  " },
    });
    submit();

    await waitFor(() =>
      expect(mocks.mutateAsync).toHaveBeenCalledWith({
        data: {
          category: "qubit",
          title: "Hello",
          content: "body",
          content_blocks: [{ id: "b1" }],
          parent_id: null,
          labels: [],
          assignee_username: null,
          chip_id: null,
          target_type: null,
          target_id: null,
          cooldown_id: null,
          task_id: null,
        },
      }),
    );
    await waitFor(() =>
      expect(mocks.push).toHaveBeenCalledWith("/forum/post-1?from=status%3Dopen"),
    );
    expect(mocks.triggerAiReply).not.toHaveBeenCalled();
  });

  it("prefers the editor snapshot and triggers the AI reply on @qdash", async () => {
    mocks.snapshot.mockResolvedValue({
      markdown: "hi @qdash",
      blocks: [{ id: "s1" }],
    });
    mocks.mutateAsync.mockResolvedValue({ data: { id: "post-2" } });
    render(<ForumNewPage />);
    fireEvent.change(screen.getByLabelText("Thread title"), {
      target: { value: "Title" },
    });
    submit();

    await waitFor(() =>
      expect(mocks.mutateAsync).toHaveBeenCalledWith({
        data: expect.objectContaining({
          content: "hi @qdash",
          content_blocks: [{ id: "s1" }],
        }),
      }),
    );
    await waitFor(() =>
      expect(mocks.triggerAiReply).toHaveBeenCalledWith(
        "post-2",
        "hi @qdash",
        expect.any(Function),
      ),
    );
  });

  it("prefills the form from search params and sends the target", async () => {
    mocks.params = new URLSearchParams({
      title: "Prefilled",
      content: "Some body",
      category: "coupling",
      labels: "a,b",
      chip_id: "64Qv3",
      target_type: "coupling",
      target_id: "0-1",
      task_id: "task-1",
    });
    mocks.mutateAsync.mockResolvedValue({ data: { id: "post-3" } });
    render(<ForumNewPage />);

    expect((screen.getByLabelText("Thread title") as HTMLInputElement).value).toBe("Prefilled");
    expect((screen.getByLabelText("Target ID") as HTMLInputElement).value).toBe("0-1");
    submit();

    await waitFor(() =>
      expect(mocks.mutateAsync).toHaveBeenCalledWith({
        data: expect.objectContaining({
          category: "coupling",
          title: "Prefilled",
          content: "Some body",
          labels: ["a", "b"],
          chip_id: "64Qv3",
          target_type: "coupling",
          target_id: "0-1",
          task_id: "task-1",
        }),
      }),
    );
  });

  it("omits the target when the target id is empty", async () => {
    mocks.params = new URLSearchParams({
      title: "T",
      content: "C",
      chip_id: "64Qv3",
    });
    mocks.mutateAsync.mockResolvedValue({ data: { id: "post-4" } });
    render(<ForumNewPage />);
    submit();

    await waitFor(() =>
      expect(mocks.mutateAsync).toHaveBeenCalledWith({
        data: expect.objectContaining({
          chip_id: null,
          target_type: null,
          target_id: null,
        }),
      }),
    );
  });

  it("shows the server error as an alert separate from field errors", async () => {
    mocks.params = new URLSearchParams({ title: "T", content: "C" });
    mocks.mutateAsync.mockRejectedValue({
      response: { data: { detail: "Thread rejected" } },
    });
    render(<ForumNewPage />);
    submit();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Thread rejected");
    expect(screen.getByLabelText("Thread title").getAttribute("aria-invalid")).toBe("false");
    expect(mocks.push).not.toHaveBeenCalled();
  });
});
