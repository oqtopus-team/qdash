import { describe, it, expect } from "vitest";

import {
  getTimezoneOffsetString,
  toIsoSeconds,
  toDateTimeLocal,
} from "../datetime";

describe("getTimezoneOffsetString", () => {
  it("returns +09:00 for Asia/Tokyo", () => {
    expect(getTimezoneOffsetString("Asia/Tokyo")).toBe("+09:00");
  });

  it("returns +00:00 for UTC", () => {
    expect(getTimezoneOffsetString("UTC")).toBe("+00:00");
  });

  it("returns a valid offset for America/New_York", () => {
    const offset = getTimezoneOffsetString("America/New_York");
    expect(offset).toMatch(/^-0[45]:00$/);
  });
});

describe("toIsoSeconds", () => {
  it("appends seconds and timezone offset to 16-char datetime", () => {
    const result = toIsoSeconds("2024-06-15T12:00");
    expect(result).toBe("2024-06-15T12:00:00+09:00");
  });

  it("returns input unchanged when length is not 16", () => {
    const input = "2024-06-15T12:00:00+09:00";
    expect(toIsoSeconds(input)).toBe(input);
  });
});

describe("toDateTimeLocal", () => {
  it("slices to first 16 chars when input contains T", () => {
    expect(toDateTimeLocal("2024-06-15T12:00:00+09:00")).toBe(
      "2024-06-15T12:00",
    );
  });

  it("appends T00:00 when input has no T", () => {
    expect(toDateTimeLocal("2024-06-15")).toBe("2024-06-15T00:00");
  });
});
