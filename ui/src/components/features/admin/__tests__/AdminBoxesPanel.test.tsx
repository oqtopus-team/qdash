import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AdminBoxesPanel,
  needsAddress,
  parseOptions,
} from "@/components/features/admin/AdminBoxesPanel";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  response: {
    layout: "shared",
    editable: true,
    boxes: [
      { box_id: "Q73A", name: "QuEL-1 #1", type: "quel1-a", address: "10.1.0.1", adapter: "1" },
    ],
    box_types: ["quel1-a", "quel3"],
  } as Record<string, unknown>,
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/config/config", () => ({
  getListConfigBoxesQueryKey: () => ["boxes"],
  useListConfigBoxes: () => ({ data: { data: mocks.response }, isLoading: false, error: null }),
  useUpsertConfigBox: () => ({ mutate: mocks.mutate, isPending: false }),
}));

describe("parseOptions", () => {
  it("splits lines and commas and drops blanks", () => {
    expect(parseOptions("a, b\n\nc")).toEqual(["a", "b", "c"]);
    expect(parseOptions(" ")).toBeUndefined();
  });
});

describe("needsAddress", () => {
  it("is true only for QuEL-1 and QuBE types", () => {
    expect(needsAddress("quel1-a")).toBe(true);
    expect(needsAddress("qube-ou")).toBe(true);
    expect(needsAddress("quel3")).toBe(false);
  });
});

describe("AdminBoxesPanel", () => {
  afterEach(() => {
    cleanup();
    mocks.mutate.mockReset();
    mocks.response = { ...mocks.response, editable: true, message: undefined };
  });

  it("lists boxes and registers a new one", async () => {
    render(<AdminBoxesPanel />);
    expect(screen.getByText("Q73A")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /register box/i }));
    fireEvent.change(screen.getByLabelText("Box ID"), { target: { value: "R21B" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "QuEL-1 #2" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "quel3" } });
    expect(screen.queryByLabelText("Address")).toBeNull();
    fireEvent.change(screen.getByLabelText(/^Options/), {
      target: { value: "skip_sync\nloopback" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        data: {
          box_id: "R21B",
          name: "QuEL-1 #2",
          type: "quel3",
          address: undefined,
          adapter: undefined,
          options: ["skip_sync", "loopback"],
        },
      }),
    );
  });

  it("edits an existing box with its id locked", async () => {
    render(<AdminBoxesPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Q73A" }));

    const idInput = (await screen.findByLabelText("Box ID")) as HTMLInputElement;
    expect(idInput.value).toBe("Q73A");
    expect(idInput.disabled).toBe(true);
    expect((screen.getByLabelText("Address") as HTMLInputElement).value).toBe("10.1.0.1");
  });

  it("explains when boxes cannot be registered", () => {
    mocks.response = {
      ...mocks.response,
      editable: false,
      message: "Boxes live under each chip in the legacy layout",
    };
    render(<AdminBoxesPanel />);
    expect(screen.getByText("Boxes live under each chip in the legacy layout")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /register box/i }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});
