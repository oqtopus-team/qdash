import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useForumLabels } from "../useForumLabels";

const mocks = vi.hoisted(() => ({
  useListForumLabels: vi.fn(),
  projectId: "project-1" as string | null,
}));

vi.mock("@/client/forum/forum", () => ({
  useListForumLabels: mocks.useListForumLabels,
  getListForumLabelsQueryKey: () => ["/forum/labels"],
}));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: mocks.projectId }),
}));

beforeEach(() => {
  mocks.projectId = "project-1";
  mocks.useListForumLabels.mockReset();
  mocks.useListForumLabels.mockReturnValue({ data: undefined, isLoading: false, isError: false });
});

describe("useForumLabels", () => {
  it("scopes the query key to the current project", () => {
    renderHook(() => useForumLabels());
    const options = mocks.useListForumLabels.mock.calls[0][0];
    expect(options.query.queryKey).toEqual(["/forum/labels", "project-1"]);
    expect(options.query.enabled).toBe(true);
  });

  it("disables the query when there is no project", () => {
    mocks.projectId = null;
    renderHook(() => useForumLabels());
    expect(mocks.useListForumLabels.mock.calls[0][0].query.enabled).toBe(false);
  });

  it("returns an empty list while there is no data", () => {
    const { result } = renderHook(() => useForumLabels());
    expect(result.current.labels).toEqual([]);
  });
});
