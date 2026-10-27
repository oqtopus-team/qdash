import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { AxiosError, AxiosHeaders } from "axios";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { FileWorkspace } from "@/lib/fileWorkspace";
import { unpublishedCount } from "@/lib/fileWorkspace";

import { useGitWorkspace } from "../useGitWorkspace";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => toast }));

function conflict(): AxiosError {
  const headers = new AxiosHeaders();
  return new AxiosError("refused", "409", { headers }, null, {
    status: 409,
    statusText: "Conflict",
    headers,
    config: { headers },
    data: { detail: "Shared configuration files have unpublished changes: config/wiring.yaml" },
  });
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("unpublishedCount", () => {
  it("adds saved files and unpushed commits", () => {
    expect(
      unpublishedCount({
        is_git_repo: true,
        changed_files: ["a", "b"],
        untracked_files: ["b", "c"],
        unpushed_commits: 1,
      }),
    ).toBe(4);
    expect(unpublishedCount({ is_git_repo: false, unpushed_commits: 3 })).toBe(0);
  });
});

describe("useGitWorkspace", () => {
  it("keeps a 409 as a conflict and retries with force on confirmation", async () => {
    const pull = vi.fn().mockRejectedValueOnce(conflict()).mockResolvedValueOnce({ commit: "abc" });
    const sync = vi
      .fn()
      .mockRejectedValueOnce(conflict())
      .mockResolvedValueOnce({
        mode: "github",
        commit: "def",
        published: ["params/64Qv3/t1.yaml"],
      });
    const workspace = {
      key: "config",
      defaultCommitMessage: "m",
      getGitStatus: vi.fn().mockResolvedValue({ is_git_repo: true }),
      pull,
      push: vi.fn(),
      sync,
    } as unknown as FileWorkspace;
    const { result } = renderHook(() => useGitWorkspace(workspace), { wrapper });

    act(() => result.current.pull());
    await waitFor(() => expect(result.current.conflict?.action).toBe("pull"));
    expect(result.current.conflict?.message).toContain("config/wiring.yaml");
    expect(toast.error).not.toHaveBeenCalled();

    act(() => result.current.forceRetry());
    await waitFor(() => expect(result.current.conflict).toBeNull());
    expect(pull).toHaveBeenLastCalledWith(true);

    act(() => result.current.sync());
    await waitFor(() => expect(result.current.conflict?.action).toBe("sync"));
    act(() => result.current.forceRetry());
    await waitFor(() => expect(result.current.conflict).toBeNull());
    expect(sync).toHaveBeenLastCalledWith(true);
    expect(toast.success).toHaveBeenLastCalledWith("Synced config: published 1 file, now at def");
  });
});
