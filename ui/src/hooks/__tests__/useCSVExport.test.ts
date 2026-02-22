import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useCSVExport } from "../useCSVExport";

describe("useCSVExport", () => {
  let mockLink: HTMLAnchorElement;
  let createObjectURLMock: ReturnType<typeof vi.fn>;
  const originalCreateElement = document.createElement.bind(document);

  beforeEach(() => {
    mockLink = originalCreateElement("a");
    vi.spyOn(mockLink, "setAttribute");
    vi.spyOn(mockLink, "click").mockImplementation(() => {});

    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") return mockLink;
      return originalCreateElement(tag);
    });
    vi.spyOn(document.body, "appendChild").mockImplementation((node) => node);
    vi.spyOn(document.body, "removeChild").mockImplementation((node) => node);

    createObjectURLMock = vi.fn().mockReturnValue("blob:mock-url");
    globalThis.URL.createObjectURL = createObjectURLMock;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("exportToCSV", () => {
    it("creates CSV with headers and data", () => {
      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportToCSV({
          filename: "test.csv",
          headers: ["Name", "Value"],
          data: [
            ["alpha", "1"],
            ["beta", "2"],
          ],
        });
      });

      expect(createObjectURLMock).toHaveBeenCalledOnce();
      const blob = createObjectURLMock.mock.calls[0][0] as Blob;
      expect(blob.type).toBe("text/csv;charset=utf-8;");

      expect(mockLink.setAttribute).toHaveBeenCalledWith("download", "test.csv");
      expect(mockLink.click).toHaveBeenCalledOnce();
    });

    it("escapes cells containing commas", () => {
      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportToCSV({
          filename: "test.csv",
          headers: ["Name"],
          data: [["hello, world"]],
        });
      });

      expect(createObjectURLMock).toHaveBeenCalledOnce();
    });

    it("escapes cells containing quotes by doubling them", () => {
      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportToCSV({
          filename: "test.csv",
          headers: ["Name"],
          data: [['say "hello"']],
        });
      });

      expect(createObjectURLMock).toHaveBeenCalledOnce();
    });

    it("escapes cells containing newlines", () => {
      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportToCSV({
          filename: "test.csv",
          headers: ["Name"],
          data: [["line1\nline2"]],
        });
      });

      expect(createObjectURLMock).toHaveBeenCalledOnce();
    });

    it("cleans up the link element after download", () => {
      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportToCSV({
          filename: "test.csv",
          headers: ["A"],
          data: [["1"]],
        });
      });

      expect(document.body.appendChild).toHaveBeenCalled();
      expect(document.body.removeChild).toHaveBeenCalled();
    });
  });

  describe("exportTimeSeriesCSV", () => {
    it("does not export when data is empty", () => {
      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportTimeSeriesCSV([], "t1", "CHIP01");
      });

      expect(createObjectURLMock).not.toHaveBeenCalled();
    });

    it("generates correct filename with chip, parameter, tag, and timestamp", () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2024-06-15T12:30:45.000Z"));

      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportTimeSeriesCSV(
          [{ time: "2024-06-15T00:00:00Z", value: 100, unit: "us", qid: "Q0" }],
          "t1",
          "CHIP01",
          "daily",
        );
      });

      expect(mockLink.setAttribute).toHaveBeenCalledWith(
        "download",
        "timeseries_CHIP01_t1_daily_20240615T123045.csv",
      );

      vi.useRealTimers();
    });

    it("uses 'unknown' and 'data' fallbacks when chip/tag are omitted", () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2024-06-15T12:30:45.000Z"));

      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportTimeSeriesCSV(
          [{ time: "2024-06-15T00:00:00Z", value: 100, unit: "us", qid: "Q0" }],
          "t1",
        );
      });

      expect(mockLink.setAttribute).toHaveBeenCalledWith(
        "download",
        "timeseries_unknown_t1_data_20240615T123045.csv",
      );

      vi.useRealTimers();
    });
  });

  describe("exportCorrelationCSV", () => {
    it("does not export when data is empty", () => {
      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportCorrelationCSV([], "t1", "t2_echo", "CHIP01");
      });

      expect(createObjectURLMock).not.toHaveBeenCalled();
    });

    it("generates correct filename for correlation export", () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2024-06-15T12:30:45.000Z"));

      const { result } = renderHook(() => useCSVExport());

      act(() => {
        result.current.exportCorrelationCSV(
          [{ time: "2024-06-15T00:00:00Z", x: 100, y: 200, xUnit: "us", yUnit: "us", qid: "Q0" }],
          "t1",
          "t2_echo",
          "CHIP01",
          "Q0",
        );
      });

      expect(mockLink.setAttribute).toHaveBeenCalledWith(
        "download",
        "correlation_CHIP01_Q0_t1_vs_t2_echo_20240615T123045.csv",
      );

      vi.useRealTimers();
    });
  });
});
