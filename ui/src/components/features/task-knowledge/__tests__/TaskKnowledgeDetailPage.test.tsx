import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaskKnowledgeDetailPage } from "../TaskKnowledgeDetailPage";

const { axiosGet, downloadArchive, toastError } = vi.hoisted(() => ({
  axiosGet: vi.fn(),
  downloadArchive: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ canEdit: false }) }));
vi.mock("@/lib/api/custom-instance", () => ({
  AXIOS_INSTANCE: { get: axiosGet },
  customInstance: vi.fn(),
}));
vi.mock("@/client/task/task", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/client/task/task")>()),
  downloadTaskKnowledgeArchive: downloadArchive,
}));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: toastError, info: vi.fn() }),
}));
vi.mock("@/components/ui/MarkdownContent", () => ({
  MarkdownContent: ({ content }: { content: string }) => <pre>{content}</pre>,
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TaskKnowledgeDetailPage taskName="CheckT1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  axiosGet.mockImplementation(async (url: string) => {
    if (url.endsWith("/knowledge/markdown")) return { data: "# CheckT1\n\nrendered" };
    return { data: { category: "one_qubit_coarse", examples: [] } };
  });
  window.URL.createObjectURL = vi.fn(() => "blob:knowledge");
  window.URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TaskKnowledgeDetailPage", () => {
  it("shows the published knowledge without editing controls", async () => {
    renderPage();
    await screen.findByText(/rendered/);

    expect(screen.queryByRole("button", { name: /edit/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /create pr/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /files/i })).toBeNull();
  });

  it("downloads the task's directory as a zip to start a draft from", async () => {
    const blob = new Blob(["zip"], { type: "application/zip" });
    downloadArchive.mockResolvedValue({ data: blob });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderPage();
    await screen.findByText(/rendered/);

    fireEvent.click(screen.getByRole("button", { name: /download zip/i }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(downloadArchive).toHaveBeenCalledWith("CheckT1");
    expect(window.URL.createObjectURL).toHaveBeenCalledWith(blob);
    expect((click.mock.instances[0] as unknown as HTMLAnchorElement).download).toBe("CheckT1.zip");
    click.mockRestore();
  });

  it("reports a failed download", async () => {
    downloadArchive.mockRejectedValue(
      new Error("Task 'CheckT1' does not have a knowledge directory"),
    );
    renderPage();
    await screen.findByText(/rendered/);

    fireEvent.click(screen.getByRole("button", { name: /download zip/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});
