import { describe, expect, it } from "vitest";

import { parseBlobErrorBody } from "@/components/features/metrics/MetricsPdfDownloadButton";
import { getApiErrorMessage } from "@/lib/utils/apiError";

function blobError(body: string, type = "application/json") {
  return Object.assign(new Error("Request failed with status code 404"), {
    response: { data: new Blob([body], { type }) },
  });
}

describe("parseBlobErrorBody", () => {
  it("parses a JSON Blob body so its detail can be read", async () => {
    const error = await parseBlobErrorBody(blobError('{"detail":"Chip chip-1 not found"}'));

    expect(getApiErrorMessage(error, "Download failed")).toBe("Chip chip-1 not found");
  });

  it("keeps the original error when the Blob body is not JSON", async () => {
    const error = await parseBlobErrorBody(blobError("Internal Server Error", "text/plain"));

    expect(getApiErrorMessage(error, "Download failed")).toBe(
      "Request failed with status code 404",
    );
  });

  it("returns errors without a Blob body unchanged", async () => {
    const error = new Error("Network Error");

    await expect(parseBlobErrorBody(error)).resolves.toBe(error);
    await expect(parseBlobErrorBody(null)).resolves.toBeNull();
  });
});
