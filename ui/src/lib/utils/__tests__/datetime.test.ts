import { describe, it, expect } from "vitest";

import {
  dateToDateInput,
  dateToDateTimeLocal,
  formatDateTime,
  formatRelativeTime,
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
    const result = toIsoSeconds("2024-06-15T12:00", "Asia/Tokyo");
    expect(result).toBe("2024-06-15T12:00:00+09:00");
  });

  it("returns input unchanged when length is not 16", () => {
    const input = "2024-06-15T12:00:00+09:00";
    expect(toIsoSeconds(input, "Asia/Tokyo")).toBe(input);
  });
});

describe("toDateTimeLocal", () => {
  it("converts UTC ISO input to configured timezone datetime-local", () => {
    expect(toDateTimeLocal("2024-06-15T03:00:00+00:00", "Asia/Tokyo")).toBe(
      "2024-06-15T12:00",
    );
  });

  it("treats timezone-less datetime input as UTC", () => {
    expect(toDateTimeLocal("2024-06-15T03:00:00", "Asia/Tokyo")).toBe(
      "2024-06-15T12:00",
    );
  });

  it("appends T00:00 when input has no T", () => {
    expect(toDateTimeLocal("2024-06-15", "Asia/Tokyo")).toBe(
      "2024-06-15T00:00",
    );
  });
});

describe("formatDateTime", () => {
  it("treats timezone-less datetime input as UTC", () => {
    expect(
      formatDateTime("2024-06-15T03:00:00", "yyyy-MM-dd HH:mm", "Asia/Tokyo"),
    ).toBe("2024-06-15 12:00");
  });
});

describe("formatRelativeTime", () => {
  it("does not apply the display timezone offset to relative differences", () => {
    const now = new Date("2024-06-15T03:05:00Z").getTime();
    const originalNow = Date.now;
    Date.now = () => now;

    try {
      expect(formatRelativeTime("2024-06-15T03:00:00", "Asia/Tokyo")).toBe(
        "5m ago",
      );
    } finally {
      Date.now = originalNow;
    }
  });
});

describe("dateToDateInput", () => {
  it("formats a Date in the configured timezone", () => {
    expect(
      dateToDateInput(new Date("2024-06-14T15:00:00.000Z"), "Asia/Tokyo"),
    ).toBe("2024-06-15");
  });
});

describe("dateToDateTimeLocal", () => {
  it("formats a Date in the configured timezone for datetime-local inputs", () => {
    expect(
      dateToDateTimeLocal(new Date("2024-06-15T03:30:00.000Z"), "Asia/Tokyo"),
    ).toBe("2024-06-15T12:30");
  });
});
