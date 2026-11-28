import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, useMutation } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ForumLabelManager } from "../ForumLabelManager";

const mocks = vi.hoisted(() => ({
  createMutateAsync: vi.fn(),
  updateLabel: vi.fn(),
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
  // A real mutation, so the scope passed by the edit form is applied.
  useUpdateForumLabel: (options?: { mutation?: { scope?: { id: string } } }) =>
    useMutation(
      { ...options?.mutation, mutationFn: (variables) => mocks.updateLabel(variables) },
      mutationClient,
    ),
  useDeleteForumLabel: () => ({ mutate: mocks.deleteMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { error: mocks.toastError } }));

const mutationClient = new QueryClient();

const LABELS = [{ id: "bug", label: "Bug", description: "Something broke", color: "#ff0000" }];

/** Returns the create form so queries do not match the inline edit form. */
const createForm = () => screen.getByRole("form", { name: "Create label" });

describe("ForumLabelManager", () => {
  afterEach(() => {
    cleanup();
    mutationClient.clear();
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
    expect(mocks.updateLabel).not.toHaveBeenCalled();
  });

  it("saves trimmed edits and closes the edit form", async () => {
    mocks.updateLabel.mockResolvedValue({});
    render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    const form = within(screen.getByRole("form", { name: "Edit label Bug" }));

    expect(form.getByLabelText<HTMLInputElement>("Name").value).toBe("Bug");
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "  Defect  " } });
    fireEvent.change(form.getByLabelText("Description"), { target: { value: "  " } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mocks.updateLabel).toHaveBeenCalledWith({
        labelKey: "bug",
        data: { name: "Defect", description: "" },
      }),
    );
    await waitFor(() => expect(screen.queryByRole("form", { name: "Edit label Bug" })).toBeNull());
    expect(mocks.invalidateQueries).toHaveBeenCalled();
  });

  it("keeps the edit form open and shows a toast when the update fails", async () => {
    mocks.updateLabel.mockRejectedValue(new Error("boom"));
    render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    const form = within(screen.getByRole("form", { name: "Edit label Bug" }));

    fireEvent.change(form.getByLabelText("Name"), { target: { value: "Defect" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith("Failed to update label"));
    expect(screen.getByRole("form", { name: "Edit label Bug" })).toBeTruthy();
  });

  it("runs a save from a reopened edit form after the earlier save of the same label", async () => {
    let resolveFirst: (value: unknown) => void = () => {};
    mocks.updateLabel
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce({});
    render(<ForumLabelManager labels={LABELS} />);

    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    let form = within(screen.getByRole("form", { name: "Edit label Bug" }));
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "First" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocks.updateLabel).toHaveBeenCalledTimes(1));
    fireEvent.click(form.getByRole("button", { name: "Cancel" }));

    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    form = within(screen.getByRole("form", { name: "Edit label Bug" }));
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "Second" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(mocks.updateLabel).toHaveBeenCalledTimes(1);

    resolveFirst({});
    await waitFor(() => expect(mocks.updateLabel).toHaveBeenCalledTimes(2));
    expect(mocks.updateLabel.mock.calls[1][0]).toEqual({
      labelKey: "bug",
      data: { name: "Second" },
    });
  });

  it("sends only the edited fields so a reopened form keeps an earlier rename", async () => {
    let resolveFirst: (value: unknown) => void = () => {};
    mocks.updateLabel
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce({});
    render(<ForumLabelManager labels={LABELS} />);

    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    let form = within(screen.getByRole("form", { name: "Edit label Bug" }));
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "Renamed" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocks.updateLabel).toHaveBeenCalledTimes(1));
    fireEvent.click(form.getByRole("button", { name: "Cancel" }));

    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    form = within(screen.getByRole("form", { name: "Edit label Bug" }));
    fireEvent.change(form.getByLabelText("Description"), { target: { value: "New text" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    resolveFirst({});
    await waitFor(() => expect(mocks.updateLabel).toHaveBeenCalledTimes(2));
    expect(mocks.updateLabel.mock.calls[1][0]).toEqual({
      labelKey: "bug",
      data: { description: "New text" },
    });
  });

  it("closes the edit form without a request when nothing was edited", async () => {
    render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    const form = within(screen.getByRole("form", { name: "Edit label Bug" }));

    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByRole("form", { name: "Edit label Bug" })).toBeNull());
    expect(mocks.updateLabel).not.toHaveBeenCalled();
  });

  it("keeps another label's edit form open when an earlier save finishes", async () => {
    let resolveSave: (value: unknown) => void = () => {};
    mocks.updateLabel.mockImplementationOnce(
      () => new Promise((resolve) => (resolveSave = resolve)),
    );
    render(<ForumLabelManager labels={[...LABELS, { ...LABELS[0], id: "idea", label: "Idea" }]} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Edit label" })[0]);
    const bugForm = within(screen.getByRole("form", { name: "Edit label Bug" }));
    fireEvent.change(bugForm.getByLabelText("Name"), { target: { value: "Defect" } });
    fireEvent.click(bugForm.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocks.updateLabel).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    expect(screen.getByRole("form", { name: "Edit label Idea" })).toBeTruthy();

    resolveSave({});
    await waitFor(() => expect(mocks.invalidateQueries).toHaveBeenCalled());
    expect(screen.getByRole("form", { name: "Edit label Idea" })).toBeTruthy();
  });

  it("keeps a reopened edit form open when the save from before Cancel finishes", async () => {
    let resolveSave: (value: unknown) => void = () => {};
    mocks.updateLabel.mockImplementationOnce(
      () => new Promise((resolve) => (resolveSave = resolve)),
    );
    render(<ForumLabelManager labels={LABELS} />);

    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    const form = within(screen.getByRole("form", { name: "Edit label Bug" }));
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "Defect" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocks.updateLabel).toHaveBeenCalledTimes(1));
    fireEvent.click(form.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));

    resolveSave({});
    await waitFor(() => expect(mocks.invalidateQueries).toHaveBeenCalled());
    expect(screen.getByRole("form", { name: "Edit label Bug" })).toBeTruthy();
  });

  it("updates untouched edit fields from refetched labels and keeps edited ones", async () => {
    const { rerender } = render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit label" }));
    let form = within(screen.getByRole("form", { name: "Edit label Bug" }));
    fireEvent.change(form.getByLabelText("Description"), { target: { value: "Edited" } });

    rerender(<ForumLabelManager labels={[{ ...LABELS[0], label: "Defect" }]} />);

    form = within(screen.getByRole("form", { name: "Edit label Defect" }));
    await waitFor(() => expect(form.getByLabelText<HTMLInputElement>("Name").value).toBe("Defect"));
    expect(form.getByLabelText<HTMLInputElement>("Description").value).toBe("Edited");
  });

  it("deletes a label after confirmation", async () => {
    render(<ForumLabelManager labels={LABELS} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete label" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));

    expect(mocks.deleteMutate).toHaveBeenCalledWith({ labelKey: "bug" }, expect.any(Object));
  });
});
