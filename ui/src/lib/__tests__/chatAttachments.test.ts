import { describe, expect, it } from "vitest";

import {
  MAX_ATTACHMENTS,
  MAX_IMAGE_EDGE,
  acceptedImageFiles,
  attachmentRoom,
  dataUrlToBase64,
  fitWithin,
  isSupportedImage,
  pastedImageFiles,
} from "@/lib/chatAttachments";

const file = (name: string, type: string) => new File(["x"], name, { type });

describe("acceptedImageFiles", () => {
  it("keeps PNG and JPEG and drops everything else", () => {
    const files = [
      file("a.png", "image/png"),
      file("b.jpg", "image/jpeg"),
      file("c.gif", "image/gif"),
      file("d.csv", "text/csv"),
    ];
    expect(acceptedImageFiles(files).map((f) => f.name)).toEqual(["a.png", "b.jpg"]);
    expect(acceptedImageFiles(null)).toEqual([]);
    expect(isSupportedImage({ type: "image/webp" })).toBe(false);
  });
});

describe("pastedImageFiles", () => {
  it("takes the file items of a paste and ignores text", () => {
    const png = file("shot.png", "image/png");
    const data = {
      items: [
        { kind: "string", getAsFile: () => null },
        { kind: "file", getAsFile: () => png },
        { kind: "file", getAsFile: () => file("x.gif", "image/gif") },
      ],
    } as unknown as DataTransfer;
    expect(pastedImageFiles(data)).toEqual([png]);
    expect(pastedImageFiles(null)).toEqual([]);
  });
});

describe("attachmentRoom", () => {
  it("counts down to zero and never goes negative", () => {
    expect(attachmentRoom(0)).toBe(MAX_ATTACHMENTS);
    expect(attachmentRoom(MAX_ATTACHMENTS - 1)).toBe(1);
    expect(attachmentRoom(MAX_ATTACHMENTS + 2)).toBe(0);
  });
});

describe("fitWithin", () => {
  it("leaves small images alone and scales large ones by the longest edge", () => {
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
    expect(fitWithin(MAX_IMAGE_EDGE, 10)).toEqual({ width: MAX_IMAGE_EDGE, height: 10 });
    expect(fitWithin(3200, 2400)).toEqual({ width: 1600, height: 1200 });
    expect(fitWithin(1000, 4000)).toEqual({ width: 400, height: 1600 });
    expect(fitWithin(0, 0)).toEqual({ width: 0, height: 0 });
  });
});

describe("dataUrlToBase64", () => {
  it("splits the mime type from the payload", () => {
    expect(dataUrlToBase64("data:image/png;base64,iVBORw0KGgo=")).toEqual({
      mimeType: "image/png",
      data: "iVBORw0KGgo=",
    });
    expect(() => dataUrlToBase64("data:text/plain,hello")).toThrow(/data URL/);
  });
});
