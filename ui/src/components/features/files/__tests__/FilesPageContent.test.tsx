import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FilesPageContent } from "@/components/features/files/FilesPageContent";

const mockPush = vi.fn();
const mockSuccess = vi.fn();
const mockError = vi.fn();
const mockInfo = vi.fn();
const mockInvalidateQueries = vi.fn();
const mockRefetch = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/client/file/file", () => ({
  getFileTree: vi.fn(() => Promise.resolve({ data: [] })),
  getFileContent: vi.fn(() => Promise.resolve({ data: { content: "" } })),
  saveFileContent: vi.fn(() => Promise.resolve({ data: {} })),
  getGitStatus: vi.fn(() => Promise.resolve({ data: {} })),
  gitPullConfig: vi.fn(() => Promise.resolve({ data: {} })),
  gitPushConfig: vi.fn(() => Promise.resolve({ data: {} })),
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mockSuccess, error: mockError, info: mockInfo }),
}));

vi.mock("@/components/ui/Skeleton/PageSkeletons", () => ({
  EditorPageSkeleton: () => <div data-testid="editor-page-skeleton" />,
}));

vi.mock("@monaco-editor/react", () => ({
  __esModule: true,
  default: () => <div data-testid="monaco-editor" />,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: undefined, isLoading: false, error: null, refetch: mockRefetch }),
  useMutation: () => ({ mutate: mockPush, isPending: false }),
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

describe("FilesPageContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the create PR button with visible overflow so its hover and focus effects are not clipped", () => {
    render(<FilesPageContent />);

    const button = screen.getByRole("button", { name: /create pr/i });
    expect(button).toHaveClass("overflow-visible");
  });
});
