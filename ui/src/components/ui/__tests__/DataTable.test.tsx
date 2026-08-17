import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DataTable } from "@/components/ui/DataTable";

interface TestRow {
  name: string;
  note: string;
  value: number;
}

const rows: TestRow[] = [
  { name: "Alpha", note: "first", value: 1 },
  { name: "Bravo", note: "second", value: 3 },
  { name: "Charlie", note: "hidden match", value: 2 },
];

const columns = [
  { key: "name", label: "Name", sortable: true },
  {
    key: "value",
    label: "Value",
    sortable: true,
    render: (value: number) => `#${value}`,
  },
];

afterEach(cleanup);

describe("DataTable", () => {
  it("sorts descending on the first sortable header click", () => {
    render(<DataTable title="Results" data={rows} columns={columns} pageSize={10} />);

    fireEvent.click(screen.getByRole("columnheader", { name: "Value" }));

    const renderedRows = screen.getAllByRole("row").slice(1);
    expect(within(renderedRows[0]).getByText("Bravo")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Value" }).getAttribute("aria-sort")).toBe(
      "descending",
    );
  });

  it("filters only by the configured search column", () => {
    render(<DataTable title="Results" data={rows} columns={columns} searchable searchKey="name" />);

    const search = screen.getByPlaceholderText("Search...");
    fireEvent.change(search, { target: { value: "brav" } });
    expect(screen.getByText("Bravo")).toBeTruthy();
    expect(screen.queryByText("Alpha")).toBeNull();
    expect(screen.getByText("1 filtered")).toBeTruthy();

    fireEvent.change(search, { target: { value: "hidden match" } });
    expect(screen.getByText("No results found")).toBeTruthy();
  });

  it("paginates rows with TanStack Table state", () => {
    render(<DataTable title="Results" data={rows} columns={columns} pageSize={2} />);

    expect(screen.getByText("2 / 3")).toBeTruthy();
    expect(screen.getByText("Alpha")).toBeTruthy();
    expect(screen.queryByText("Charlie")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Charlie")).toBeTruthy();
    expect(screen.getByText("2/2")).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Next" }).disabled).toBe(true);
  });

  it("renders custom cells without hiding zero values", () => {
    const zeroRows = [{ name: "Zero", note: "", value: 0 }];
    render(<DataTable title="Results" data={zeroRows} columns={columns} />);

    expect(screen.getByText("#0")).toBeTruthy();
  });
});
