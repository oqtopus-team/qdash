import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  MAX_TOTAL_IMAGE_DATA_LENGTH,
  stageAttachment,
  type StagedAttachment,
} from "@/lib/chatAttachments";
import { useChatAttachments } from "../useChatAttachments";

vi.mock("@/lib/chatAttachments", async (original) => ({
  ...(await original<typeof import("@/lib/chatAttachments")>()),
  stageAttachment: vi.fn(),
}));
const stage = vi.mocked(stageAttachment);
const file = (name: string) => new File(["x"], name, { type: "image/png" });
const image = (name: string): StagedAttachment => ({
  id: name,
  name,
  data: "eA==",
  mimeType: "image/png",
  previewUrl: "data:image/png;base64,eA==",
});
beforeEach(() => {
  stage.mockReset();
});
afterEach(cleanup);

function deferred() {
  let resolve!: (value: StagedAttachment) => void;
  const promise = new Promise<StagedAttachment>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("useChatAttachments", () => {
  it("reserves slots across rapid batches and preserves selection order", async () => {
    const first = deferred();
    stage
      .mockImplementationOnce(() => first.promise)
      .mockImplementation(async (f) => image(f.name));
    const { result } = renderHook(() => useChatAttachments("s1"));
    act(() => {
      result.current.attach([file("a"), file("b"), file("c")]);
      expect(result.current.isPending()).toBe(true);
      result.current.attach([file("d"), file("e")]);
    });
    expect(result.current.isStaging).toBe(true);
    await act(async () => first.resolve(image("a")));
    await waitFor(() => expect(result.current.isStaging).toBe(false));
    expect(result.current.attachments.map((a) => a.name)).toEqual(["a", "b", "c", "d"]);
    expect(stage).toHaveBeenCalledTimes(4);
    expect(result.current.notice).toMatch(/Up to 4/);
  });

  it("reports failures and still stages the remaining files", async () => {
    stage.mockRejectedValueOnce(new Error("Image is too large")).mockResolvedValueOnce(image("b"));
    const { result } = renderHook(() => useChatAttachments("s1"));
    act(() => result.current.attach([file("a"), file("b")]));
    await waitFor(() => expect(result.current.isPending()).toBe(false));
    expect(result.current.attachments.map((a) => a.name)).toEqual(["b"]);
    expect(result.current.notice).toBe("Image is too large");
  });

  it("enforces the combined size across batches and releases space after removal", async () => {
    stage.mockImplementation(async (f) => ({
      ...image(f.name),
      data: "x".repeat(MAX_TOTAL_IMAGE_DATA_LENGTH / 2),
    }));
    const { result } = renderHook(() => useChatAttachments("s1"));
    act(() => result.current.attach([file("a"), file("b")]));
    await waitFor(() => expect(result.current.isPending()).toBe(false));
    act(() => result.current.attach([file("c")]));
    await waitFor(() => expect(result.current.notice).toMatch(/too large together/));
    expect(result.current.attachments).toHaveLength(2);
    act(() => {
      result.current.remove("a");
      result.current.attach([file("c")]);
    });
    await waitFor(() => expect(result.current.attachments.map((a) => a.name)).toEqual(["b", "c"]));
  });

  it("discards pending results when switching sessions", async () => {
    const first = deferred();
    stage.mockReturnValue(first.promise);
    const { result, rerender } = renderHook(({ id }) => useChatAttachments(id), {
      initialProps: { id: "s1" },
    });
    act(() => result.current.attach([file("a")]));
    await waitFor(() => expect(stage).toHaveBeenCalledOnce());
    rerender({ id: "s2" });
    await act(async () => first.resolve(image("a")));
    expect(result.current.attachments).toEqual([]);
    expect(result.current.isPending()).toBe(false);
  });
});
