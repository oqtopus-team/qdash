import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaskKnowledgeDetailPage } from "../TaskKnowledgeDetailPage";

const { axiosGet, saveContent, getContent, projectState } = vi.hoisted(() => ({
  axiosGet: vi.fn(),
  saveContent: vi.fn(),
  getContent: vi.fn(),
  projectState: { canEdit: true },
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => projectState }));
vi.mock("@/lib/api/custom-instance", () => ({
  AXIOS_INSTANCE: { get: axiosGet },
  customInstance: vi.fn(),
}));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));
vi.mock("@/components/ui/MarkdownContent", () => ({
  MarkdownContent: ({ content }: { content: string }) => <pre>{content}</pre>,
}));
vi.mock("@/components/ui/MarkdownEditor", () => ({
  MarkdownEditor: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <textarea aria-label="knowledge" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));
vi.mock("@/components/ui/FileDiffReviewDialog", () => ({ FileDiffReviewDialog: () => null }));
vi.mock("@/lib/fileWorkspace", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/fileWorkspace")>();
  return {
    ...actual,
    KNOWLEDGE_WORKSPACE: {
      ...actual.KNOWLEDGE_WORKSPACE,
      getContent,
      saveContent,
      getGitStatus: async () => ({ is_git_repo: true, branch: "main", commit: "abc12345" }),
    },
  };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TaskKnowledgeDetailPage taskName="CheckT1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  projectState.canEdit = true;
  axiosGet.mockImplementation(async (url: string) => {
    if (url.endsWith("/knowledge/markdown")) return { data: "# CheckT1\n\nrendered" };
    return { data: { category: "td-characterization", cases: [] } };
  });
  getContent.mockResolvedValue({
    content: "# CheckT1\n\nsource",
    base_content: "# CheckT1\n\nsource",
    is_saved_change: false,
    path: "td-characterization/CheckT1/index.md",
  });
  saveContent.mockResolvedValue({ message: "ok", path: "td-characterization/CheckT1/index.md" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TaskKnowledgeDetailPage", () => {
  it("edits the task's index.md in the knowledge repository and saves it there", async () => {
    renderPage();
    await screen.findByText(/rendered/);

    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const editor = await screen.findByLabelText("knowledge");
    expect((editor as HTMLTextAreaElement).value).toBe("# CheckT1\n\nsource");
    expect(getContent).toHaveBeenCalledWith("td-characterization/CheckT1/index.md");

    fireEvent.change(editor, { target: { value: "# CheckT1\n\nsource edited" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(saveContent).toHaveBeenCalledWith(
        "td-characterization/CheckT1/index.md",
        "# CheckT1\n\nsource edited",
      ),
    );
    // Back to the rendered view once saved.
    await screen.findByText(/rendered/);
    expect(screen.queryByLabelText("knowledge")).toBeNull();
  });

  it("links the file browser to the task's folder", async () => {
    renderPage();
    await screen.findByText(/rendered/);

    expect(screen.getByRole("link", { name: /files/i }).getAttribute("href")).toBe(
      "/knowledge/files?path=td-characterization%2FCheckT1%2Findex.md",
    );
  });

  it("keeps viewers read-only", async () => {
    projectState.canEdit = false;
    renderPage();
    await screen.findByText(/rendered/);

    expect(screen.queryByRole("button", { name: /edit/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /create pr/i })).toBeNull();
  });
});
