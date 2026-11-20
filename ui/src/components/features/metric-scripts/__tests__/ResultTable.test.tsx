import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResultTable, resultToCsv } from "../render/ResultTable";
import { evaluateResponse, pairCell } from "./fixtures";

const mocks = vi.hoisted(() => ({ copyText: vi.fn(), success: vi.fn(), error: vi.fn() }));

vi.mock("@/lib/utils/clipboard", () => ({ copyText: mocks.copyText }));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mocks.success, error: mocks.error }),
}));

const cells = [
  pairCell("10", "11", { value: 97.5, assessment: { count: 4 }, label: "median of 4" }),
  pairCell("2", "3", { value: 99.1, assessment: { count: 12 }, label: "median, with comma" }),
  pairCell("2", "1", { status: "empty", assessment: { count: 1 }, label: "too few" }),
  pairCell("0", "1", { status: "error", message: "KeyError: 'zx90'" }),
];
const result = evaluateResponse("pair", cells);

function rowKeys(): string[] {
  return within(screen.getByTestId("result-table"))
    .getAllByRole("row")
    .slice(1)
    .map((row) => row.getAttribute("data-cell-key") ?? "");
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ResultTable", () => {
  it("sorts by target numerically, then by value with empty values last", () => {
    render(<ResultTable result={result} onSelectCell={vi.fn()} />);
    expect(rowKeys()).toEqual(["0>1", "2>1", "2>3", "10>11"]);

    fireEvent.click(screen.getByRole("button", { name: /^Value/ }));
    expect(rowKeys()).toEqual(["10>11", "2>3", "0>1", "2>1"]);
    expect(screen.getByRole("columnheader", { name: /^Value/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );

    fireEvent.click(screen.getByRole("button", { name: /^Value/ }));
    expect(rowKeys()).toEqual(["2>3", "10>11", "0>1", "2>1"]);

    fireEvent.click(screen.getByRole("button", { name: /^Count/ }));
    expect(rowKeys()).toEqual(["2>1", "10>11", "2>3", "0>1"]);

    fireEvent.click(screen.getByRole("button", { name: /^Status/ }));
    expect(rowKeys()[0]).toBe("0>1");
  });

  it("opens a cell from its row", () => {
    const onSelect = vi.fn();
    render(<ResultTable result={result} onSelectCell={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "Q10 → Q11" }));
    expect(onSelect).toHaveBeenCalledWith(cells[0]);
  });

  it("copies the sorted rows as CSV", async () => {
    mocks.copyText.mockResolvedValue(undefined);
    render(<ResultTable result={result} onSelectCell={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy CSV" }));

    await waitFor(() => expect(mocks.success).toHaveBeenCalledWith("Copied as CSV"));
    const csv = mocks.copyText.mock.calls[0][0] as string;
    const lines = csv.split("\n");
    expect(lines[0]).toBe("key,source,target,hops,value,unit,status,count,label");
    expect(lines[1]).toBe("0>1,0,1,1,,,error,,KeyError: 'zx90'");
    expect(lines[3]).toBe('2>3,2,3,1,99.1,%,ok,12,"median, with comma"');
  });
});

describe("resultToCsv", () => {
  it("quotes fields with quotes and line breaks", () => {
    const csv = resultToCsv([pairCell("0", "1", { label: 'say "hi"\nnow' })], "%");
    expect(csv.split("\n").slice(1).join("\n")).toBe('0>1,0,1,1,,,ok,,"say ""hi""\nnow"');
  });
});
