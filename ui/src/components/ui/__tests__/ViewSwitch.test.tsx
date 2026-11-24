import { useState } from "react";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ViewSwitch, type ViewSwitchItem } from "@/components/ui/ViewSwitch";

type View = "1q" | "2q" | "mux";

const BASE_ITEMS: ViewSwitchItem<View>[] = [
  { value: "1q", label: "Qubit" },
  { value: "2q", label: "Coupling" },
];
const MUX_ITEM: ViewSwitchItem<View> = { value: "mux", label: "MUX View" };

function ControlledSwitch({
  initial = "1q",
  hasMux = true,
  onChange,
}: {
  initial?: View;
  hasMux?: boolean;
  onChange?: (view: View) => void;
}) {
  const [view, setView] = useState<View>(initial);
  return (
    <>
      <ViewSwitch
        ariaLabel="Chip view"
        value={view}
        onValueChange={(next) => {
          setView(next);
          onChange?.(next);
        }}
        items={hasMux ? [...BASE_ITEMS, MUX_ITEM] : BASE_ITEMS}
      />
      <p>Showing {view}</p>
    </>
  );
}

function selectedTab() {
  return screen.getByRole("tab", { selected: true });
}

describe("ViewSwitch", () => {
  afterEach(() => cleanup());

  it("renders a labeled megamenu tab list with the selected tab marked", () => {
    render(<ControlledSwitch initial="2q" />);

    const tablist = screen.getByRole("tablist", { name: "Chip view" });
    expect(tablist.classList.contains("megamenu")).toBe(true);
    expect(tablist.querySelector(".megamenu-active")?.getAttribute("aria-hidden")).toBe("true");
    expect(selectedTab().textContent).toBe("Coupling");
    expect(screen.getAllByRole("tab").map((tab) => tab.getAttribute("tabindex"))).toEqual([
      "-1",
      "0",
      "-1",
    ]);
  });

  it("switches the inline view and preserves repeat-click actions on the selected tab", () => {
    const onChange = vi.fn();
    render(<ControlledSwitch onChange={onChange} />);

    fireEvent.click(screen.getByRole("tab", { name: "MUX View" }));
    expect(screen.getByText("Showing mux")).toBeTruthy();
    expect(selectedTab().textContent).toBe("MUX View");

    fireEvent.click(screen.getByRole("tab", { name: "MUX View" }));
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenLastCalledWith("mux");
  });

  it("moves focus and selection with arrow, Home, and End keys", () => {
    render(<ControlledSwitch />);
    const qubit = screen.getByRole("tab", { name: "Qubit" });
    qubit.focus();

    fireEvent.keyDown(qubit, { key: "ArrowRight" });
    expect(document.activeElement?.textContent).toBe("Coupling");
    expect(screen.getByText("Showing 2q")).toBeTruthy();

    fireEvent.keyDown(document.activeElement as Element, { key: "End" });
    expect(document.activeElement?.textContent).toBe("MUX View");

    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowRight" });
    expect(document.activeElement?.textContent).toBe("Qubit");
    expect(screen.getByText("Showing 1q")).toBeTruthy();

    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowLeft" });
    expect(document.activeElement?.textContent).toBe("MUX View");

    fireEvent.keyDown(document.activeElement as Element, { key: "Home" });
    expect(selectedTab().textContent).toBe("Qubit");
  });

  it("omits a conditional item and keeps the first tab focusable for an absent value", () => {
    render(<ControlledSwitch initial="mux" hasMux={false} />);

    expect(screen.queryByRole("tab", { name: "MUX View" })).toBeNull();
    expect(screen.queryByRole("tab", { selected: true })).toBeNull();
    expect(screen.getByRole("tab", { name: "Qubit" }).getAttribute("tabindex")).toBe("0");

    const coupling = screen.getByRole("tab", { name: "Coupling" });
    coupling.focus();
    fireEvent.keyDown(coupling, { key: "ArrowRight" });
    expect(document.activeElement?.textContent).toBe("Qubit");
  });

  it("names icon tabs whose text is visually hidden", () => {
    render(
      <ViewSwitch
        ariaLabel="Grid view"
        size="sm"
        value="pan-zoom"
        onValueChange={() => {}}
        items={[
          {
            value: "pan-zoom",
            label: <span className="hidden sm:inline">Zoom</span>,
            ariaLabel: "Zoom",
          },
          {
            value: "region",
            label: <span className="hidden sm:inline">Lock</span>,
            ariaLabel: "Lock",
          },
        ]}
      />,
    );

    expect(
      screen.getByRole("tablist", { name: "Grid view" }).classList.contains("megamenu-sm"),
    ).toBe(true);
    expect(screen.getByRole("tab", { name: "Lock" }).getAttribute("aria-selected")).toBe("false");
  });
});
