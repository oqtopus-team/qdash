import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FilesBulkDownloadButton } from "../FilesBulkDownloadButton";

const { downloadZipFileMock } = vi.hoisted(() => ({
  downloadZipFileMock: vi.fn(),
}));

vi.mock("@/client/file/file", () => ({
  downloadZipFile: downloadZipFileMock,
}));

describe("FilesBulkDownloadButton", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    downloadZipFileMock.mockReset();
  });

  it("downloads the complete config tree with the server filename", async () => {
    downloadZipFileMock.mockResolvedValue({
      data: new Blob(["zip-bytes"]),
      headers: { "content-disposition": 'attachment; filename="qubex-config_20261004.zip"' },
    });
    const createObjectURLMock = vi.fn().mockReturnValue("blob:config-archive");
    const revokeObjectURLMock = vi.fn();
    globalThis.URL.createObjectURL = createObjectURLMock as unknown as typeof URL.createObjectURL;
    globalThis.URL.revokeObjectURL = revokeObjectURLMock as unknown as typeof URL.revokeObjectURL;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const appendChildSpy = vi.spyOn(document.body, "appendChild");
    const onError = vi.fn();

    render(<FilesBulkDownloadButton onError={onError} />);
    fireEvent.click(screen.getByRole("button", { name: "Download" }));

    await waitFor(() => {
      expect(downloadZipFileMock).toHaveBeenCalledWith({ path: "." }, { responseType: "blob" });
    });
    await waitFor(() => expect(clickSpy).toHaveBeenCalledOnce());

    expect(createObjectURLMock).toHaveBeenCalledOnce();
    const link = appendChildSpy.mock.calls
      .map(([node]) => node)
      .find((node): node is HTMLAnchorElement => node instanceof HTMLAnchorElement);
    expect(link?.download).toBe("qubex-config_20261004.zip");
    expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:config-archive");
    expect(onError).not.toHaveBeenCalled();
  });

  it("reports API errors and enables the button again", async () => {
    downloadZipFileMock.mockRejectedValue({
      response: {
        data: new Blob([JSON.stringify({ detail: "Config directory not found" })], {
          type: "application/json",
        }),
      },
    });
    const onError = vi.fn();

    render(<FilesBulkDownloadButton onError={onError} />);
    const button = screen.getByRole("button", { name: "Download" });
    fireEvent.click(button);

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith("Config directory not found");
    });
    expect(button).not.toBeDisabled();
  });
});
