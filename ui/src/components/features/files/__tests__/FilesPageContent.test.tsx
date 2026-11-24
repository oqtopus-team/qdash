import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FileWorkspace } from "@/lib/fileWorkspace";

import { FilesPageContent } from "../FilesPageContent";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams("path=settings.yaml"),
}));

// The Monaco editor, as a textarea showing the loaded source.
vi.mock("next/dynamic", () => ({
  default: () => (props: { value?: string }) => (
    <textarea aria-label="Editor" readOnly value={props.value ?? ""} />
  ),
}));

vi.mock("@/components/ui/PierreFileTree", () => ({ PierreFileTree: () => null }));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

vi.mock("../useGitWorkspace", () => ({
  useGitWorkspace: () => ({
    status: { is_git_repo: false },
    refetchStatus: vi.fn(),
    pull: vi.fn(),
    push: vi.fn(),
    dismissPr: vi.fn(),
    prResult: null,
    isPulling: false,
    isPushing: false,
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// An Axios error carrying an API error body, as the client rejects with.
function apiError(status: number, data: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status, data },
  });
}

function renderPage(getContent: FileWorkspace["getContent"]) {
  const workspace = {
    key: "config",
    title: "Config Files",
    editorPath: "/config",
    defaultCommitMessage: "Update config files from UI",
    seedImport: false,
    bulkDownload: false,
    getTree: async () => [{ name: "settings.yaml", path: "settings.yaml", type: "file" }],
    getContent,
  } as unknown as FileWorkspace;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FilesPageContent workspace={workspace} />
    </QueryClientProvider>,
  );
}

describe("FilesPageContent file loading", () => {
  it("shows the public message and error ID of an unexpected read failure", async () => {
    renderPage(async () => {
      throw apiError(500, {
        detail: "Failed to read the file",
        code: "file_read_failed",
        error_id: "feedfacefeedfacefeedfacefeedface",
      });
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Failed to load settings.yaml: Failed to read the file (Error ID: feedfacefeedfacefeedfacefeedface)",
    );
    expect(screen.queryByLabelText("Editor")).toBeNull();
  });

  it("shows the detail of an expected error without an error ID", async () => {
    renderPage(async () => {
      throw apiError(400, { detail: "File is not a text file" });
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Failed to load settings.yaml: File is not a text file",
    );
    expect(screen.queryByText(/Error ID/)).toBeNull();
  });

  it("opens a file that loads in the editor", async () => {
    renderPage(async () => ({
      content: "a: 1\n",
      base_content: "a: 1\n",
      is_saved_change: false,
      path: "settings.yaml",
      name: "settings.yaml",
      size: 5,
      modified: "",
    }));

    expect(await screen.findByLabelText("Editor")).toHaveValue("a: 1\n");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
