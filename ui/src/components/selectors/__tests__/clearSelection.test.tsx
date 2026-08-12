import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DateSelector } from "@/components/selectors/DateSelector";
import { ParameterSelector } from "@/components/selectors/ParameterSelector";
import { TaskSelector } from "@/components/selectors/TaskSelector";

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: {
      data: { chips: [{ chip_id: "chip-1", installed_at: null, activity_status: "active" }] },
    },
    isLoading: false,
    isError: false,
  }),
  useGetChipDates: () => ({
    data: { data: { data: ["20260701"] } },
    isLoading: false,
    isError: false,
  }),
}));

afterEach(cleanup);

/**
 * Renders a selector inside a parent that owns the selection state, plus a
 * button that clears it — the same shape as the filter bars that expose a
 * "Clear filter" button next to the selector.
 */
function renderWithClearButton(
  renderSelector: (value: string, onSelect: (value: string) => void) => React.ReactElement,
) {
  function Harness() {
    const [value, setValue] = useState("");
    return (
      <div>
        {renderSelector(value, setValue)}
        <button type="button" onClick={() => setValue("")}>
          Clear
        </button>
      </div>
    );
  }

  render(<Harness />);
}

function pickOption(label: string) {
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "ArrowDown" });
  fireEvent.click(screen.getByText(label));
}

function clearSelection() {
  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
}

describe.each([
  {
    name: "ChipSelector",
    placeholder: "Select a chip",
    optionLabel: "chip-1",
    render: (value: string, onSelect: (value: string) => void) => (
      <ChipSelector selectedChip={value} onChipSelect={onSelect} />
    ),
  },
  {
    name: "TaskSelector",
    placeholder: "Select a task",
    optionLabel: "task-a",
    render: (value: string, onSelect: (value: string) => void) => (
      <TaskSelector tasks={[{ name: "task-a" }]} selectedTask={value} onTaskSelect={onSelect} />
    ),
  },
  {
    name: "DateSelector",
    placeholder: "Select a date",
    optionLabel: "2026/07/01",
    render: (value: string, onSelect: (value: string) => void) => (
      <DateSelector chipId="chip-1" selectedDate={value} onDateSelect={onSelect} />
    ),
  },
  {
    name: "ParameterSelector",
    placeholder: "Select parameter",
    optionLabel: "param-a",
    render: (value: string, onSelect: (value: string) => void) => (
      <ParameterSelector
        parameters={["param-a"]}
        selectedParameter={value}
        onParameterSelect={onSelect}
      />
    ),
  },
])("$name", ({ placeholder, optionLabel, render: renderSelector }) => {
  it("shows the picked option", () => {
    renderWithClearButton(renderSelector);
    pickOption(optionLabel);

    expect(screen.queryByText(optionLabel)).toBeTruthy();
  });

  it("falls back to the placeholder once the parent clears the selection", () => {
    renderWithClearButton(renderSelector);
    pickOption(optionLabel);
    clearSelection();

    // Passing `undefined` here would flip react-select into uncontrolled mode
    // and keep the stale selection on screen.
    expect(screen.queryByText(optionLabel)).toBeNull();
    expect(screen.queryByText(placeholder)).toBeTruthy();
  });
});
