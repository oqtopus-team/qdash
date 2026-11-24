import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ForumLabelManager } from "../ForumLabelManager";

const mocks = vi.hoisted(() => ({
  createMutateAsync: vi.fn(),
  updateMutateAsync: vi.fn(),
  deleteMutate: vi.fn(),
  invalidateQueries: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}));

vi.mock("@/client/forum/forum", () => ({
  getListForumLabelsQueryKey: () => ["/forum/labels"],
  useCreateForumLabel: () => ({ mutateAsync: mocks.createMutateAsync, isPending: false }),
  useUpdateForumLabel: () => ({ mutateAsync: mocks.updateMutateAsync, isPending: false }),
  useDeleteForumLabel: () => ({ mutate: mocks.deleteMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { error: mocks.toastError } }));

const LABELS = [{ id: "bug", label: "Bug", description: "Something broke", color: "#ff0000" }];

/** Returns the create form so queries do not match the inline edit form. */
const createForm = () => screen.getByRole("form", { name: "Create label" });

describe("ForumLabelManager", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows field errors and skips the request for an invalid new label", async () => {
    render(<ForumLabelManager labels={LABELS} />);
    const form = within(createForm());

    fireEvent.change(form.getByLabelText("Description"), {
      target: { value: "x".repeat(201) },
    });
    fireEvent.click(form.getByRole("button", { name: "Add" }));

    expect(await form.findByText("Name is required")).toBeTruthy();
    expect(form.getByText("Description must be 200 characters or fewer")).toBeTruthy();
    const name = form.getByLabelText("Name");
    expect(name.getAttribute("aria-invalid")).toBe("true");
    const errorId = name.getAttribute("aria-describedby");
    expect(errorId && document.getElementById(errorId)?.textContent).toBe("Name is required");
    expect(mocks.createMutateAsync).not.toHaveBeenCalled();
  });

  it("rejects a name longer than 80 characters", async () => {
    render(<ForumLabelManager labels={LABELS} />);
    const form = within(createForm());

    fireEvent.change(form.getByLabelText("Name"), { target: { value: "n".repeat(81) } });
    fireEvent.click(form.getByRole("button", { name: "Add" }));

    expect(await form.findByText("Name must be 80 characters or fewer")).toBeTruthy();
    expect(mocks.createMutateAsync).not.toHaveBeenCalled();
  });

  it("creates a label with trimmed values and resets the form", async () => {
    mocks.createMutateAsync.mockResolvedValue({});
    render(<ForumLabelManager labels={LABELS} />);
    const form = within(createForm());

    fireEvent.change(form.getByLabelText("Name"), { target: { value: "  Hardware  " } });
    fireEvent.change(form.getByLabelText("Description"), { target: { value: "   " } });
    fireEvent.change(form.getByLabelText("Label color"), { target: { value: "#00aa00" } });
    fireEvent.click(form.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(mocks.createMutateAsync).toHaveBeenCalledWith({
        data: { name: "Hardware", description: undefined, color: "#00aa00" },
      }),
    );
    await waitFor(() => expect(form.getByLabelText<HTMLInputElement>("Name").value).toBe(""));
    expect(mocks.invalidateQueries).toHaveBeenCalled();
  });

  it("keeps the values and shows a toast when creation fails", async () => {
    mocks.createMutateAsync.mockRejectedValue(new Error("boom"));
    render(<ForumLabelManager labels={LABELS} />);
    const form = within(createForm());

    fireEvent.change(form.getByLabelText("Name"), { target: { value: "Hardware" } });
    fireEvent.click(form.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith("Failed to create label"));
    expect(form.getByLabelText<HTMLInputElement>("Name").value).toBe("Hardware");
    expect(mocks.invalidateQueries).not.toHaveBeenCalled();
  });

  it("shows a field error and skips the request for an invalid edit", async () => {
    render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    const form = within(screen.getByRole("form", { name: "Edit label Bug" }));

    fireEvent.change(form.getByLabelText("Name"), { target: { value: "   " } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    expect(await form.findByText("Name is required")).toBeTruthy();
    expect(form.getByLabelText("Name").getAttribute("aria-invalid")).toBe("true");
    expect(mocks.updateMutateAsync).not.toHaveBeenCalled();
  });

  it("saves trimmed edits and closes the edit form", async () => {
    mocks.updateMutateAsync.mockResolvedValue({});
    render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    const form = within(screen.getByRole("form", { name: "Edit label Bug" }));

    expect(form.getByLabelText<HTMLInputElement>("Name").value).toBe("Bug");
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "  Defect  " } });
    fireEvent.change(form.getByLabelText("Description"), { target: { value: "  " } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mocks.updateMutateAsync).toHaveBeenCalledWith({
        labelKey: "bug",
        data: { name: "Defect", description: "", color: "#ff0000" },
      }),
    );
    await waitFor(() => expect(screen.queryByRole("form", { name: "Edit label Bug" })).toBeNull());
    expect(mocks.invalidateQueries).toHaveBeenCalled();
  });

  it("keeps the edit form open and shows a toast when the update fails", async () => {
    mocks.updateMutateAsync.mockRejectedValue(new Error("boom"));
    render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    const form = within(screen.getByRole("form", { name: "Edit label Bug" }));

    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith("Failed to update label"));
    expect(screen.getByRole("form", { name: "Edit label Bug" })).toBeTruthy();
  });

  it("deletes a label after confirmation", async () => {
    render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete label" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));

    expect(mocks.deleteMutate).toHaveBeenCalledWith({ labelKey: "bug" }, expect.any(Object));
  });
});
