import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KnowledgeDraftDownloadButton } from "../KnowledgeDraftDownloadButton";

const { downloadArchive, saveBlob, toastError } = vi.hoisted(() => ({
  downloadArchive: vi.fn(),
  saveBlob: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock("@/client/evaluation/evaluation", () => ({
  downloadKnowledgeDraftArchive: downloadArchive,
}));
vi.mock("@/lib/utils/download", () => ({ saveBlob }));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => ({ error: toastError }) }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KnowledgeDraftDownloadButton", () => {
  it("saves the run's draft zip under its uploaded name", async () => {
    const blob = new Blob(["zip"], { type: "application/zip" });
    downloadArchive.mockResolvedValue({ data: blob });
    render(<KnowledgeDraftDownloadButton draftId={"ab".repeat(32)} filename="rabi.zip" />);

    fireEvent.click(screen.getByRole("button", { name: /download zip/i }));

    await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(blob, "rabi.zip"));
    expect(downloadArchive).toHaveBeenCalledWith("ab".repeat(32));
  });

  it("reports a draft that cannot be downloaded", async () => {
    downloadArchive.mockRejectedValue({
      response: { data: { detail: "knowledge draft x not found" } },
    });
    render(<KnowledgeDraftDownloadButton draftId="x" filename="x.zip" />);

    fireEvent.click(screen.getByRole("button", { name: /download zip/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith("knowledge draft x not found"));
    expect(saveBlob).not.toHaveBeenCalled();
  });
});
