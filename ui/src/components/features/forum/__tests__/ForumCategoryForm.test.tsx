import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ForumCategoryForm } from "../ForumCategoryForm";

const mocks = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  invalidateQueries: vi.fn(),
}));

vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}));

vi.mock("@/client/forum/forum", () => ({
  getListForumCategoriesQueryKey: () => ["forum-categories"],
  useCreateForumCategory: () => ({ mutateAsync: mocks.mutateAsync, isPending: false }),
}));

/** Sets an input or select value by its accessible label. */
function change(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

/** Clicks the Add button. */
function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
}

describe("ForumCategoryForm", () => {
  beforeEach(() => {
    mocks.mutateAsync.mockResolvedValue({ data: {} });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows required errors and does not submit an empty form", async () => {
    render(<ForumCategoryForm />);
    submit();

    expect(await screen.findByText("Key is required")).toBeTruthy();
    expect(screen.getByText("Name is required")).toBeTruthy();
    const keyInput = screen.getByLabelText("Category key");
    expect(keyInput.getAttribute("aria-invalid")).toBe("true");
    expect(keyInput.getAttribute("aria-describedby")).toBe("forum-category-key-error");
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("treats a whitespace-only name as missing", async () => {
    render(<ForumCategoryForm />);
    change("Category key", "hardware");
    change("Category name", "   ");
    submit();

    expect(await screen.findByText("Name is required")).toBeTruthy();
    const nameInput = screen.getByLabelText("Category name");
    expect(nameInput.getAttribute("aria-invalid")).toBe("true");
    expect(nameInput.getAttribute("aria-describedby")).toBe("forum-category-name-error");
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it.each(["Bad Key", "-hardware", "_hardware"])(
    "rejects the key %j that does not match the API pattern",
    async (key) => {
      render(<ForumCategoryForm />);
      change("Category key", key);
      change("Category name", "Hardware");
      submit();

      expect(
        await screen.findByText("Use a-z, 0-9, - or _, starting with a-z or 0-9"),
      ).toBeTruthy();
      expect(mocks.mutateAsync).not.toHaveBeenCalled();
    },
  );

  it("accepts values at the API limits", async () => {
    render(<ForumCategoryForm />);
    change("Category key", "a".repeat(64));
    change("Category name", "n".repeat(80));
    change("Category description", "d".repeat(200));
    submit();

    await waitFor(() => expect(mocks.mutateAsync).toHaveBeenCalledTimes(1));
    expect(mocks.mutateAsync.mock.calls[0][0].data).toMatchObject({
      key: "a".repeat(64),
      name: "n".repeat(80),
      description: "d".repeat(200),
    });
  });

  it("rejects values that exceed the API limits", async () => {
    render(<ForumCategoryForm />);
    change("Category key", "a".repeat(65));
    change("Category name", "n".repeat(81));
    change("Category description", "d".repeat(201));
    submit();

    expect(await screen.findByText("Key must be 64 characters or fewer")).toBeTruthy();
    expect(screen.getByText("Name must be 80 characters or fewer")).toBeTruthy();
    expect(screen.getByText("Description must be 200 characters or fewer")).toBeTruthy();
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("submits trimmed values, resets the form, and refreshes categories", async () => {
    render(<ForumCategoryForm />);
    change("Category key", "  hardware  ");
    change("Category name", "  Hardware  ");
    change("Category description", "  Wiring and devices  ");
    change("Category color", "warning");
    change("Category icon", "circuit-board");
    submit();

    await waitFor(() => expect(mocks.mutateAsync).toHaveBeenCalledTimes(1));
    expect(mocks.mutateAsync).toHaveBeenCalledWith({
      data: {
        key: "hardware",
        name: "Hardware",
        description: "Wiring and devices",
        color: "warning",
        icon: "circuit-board",
        sort_order: null,
      },
    });
    await waitFor(() =>
      expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["forum-categories"] }),
    );
    expect((screen.getByLabelText("Category key") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Category color") as HTMLSelectElement).value).toBe("neutral");
  });

  it("shows API failures as a server error and keeps the input", async () => {
    mocks.mutateAsync.mockRejectedValue({
      response: { status: 409, data: { detail: "Category already exists" } },
    });
    render(<ForumCategoryForm />);
    change("Category key", "hardware");
    change("Category name", "Hardware");
    submit();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Category already exists");
    expect((screen.getByLabelText("Category key") as HTMLInputElement).value).toBe("hardware");
    expect(mocks.invalidateQueries).not.toHaveBeenCalled();
  });
});
