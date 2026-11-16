import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateUserModal } from "@/components/features/admin/CreateUserModal";

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: toastError }),
}));

/** Simulates an insecure HTTP origin, where browsers do not expose `navigator.clipboard`. */
function stubInsecureClipboard(execResult: boolean) {
  vi.stubGlobal(
    "navigator",
    new Proxy(navigator, {
      get(target, property) {
        if (property === "clipboard") return undefined;
        return Reflect.get(target, property, target);
      },
    }),
  );
  const copiedFrom: Array<{ value: string; inDialog: boolean }> = [];
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    writable: true,
    value: vi.fn(() => {
      const textarea = document.activeElement;
      if (textarea instanceof HTMLTextAreaElement) {
        copiedFrom.push({
          value: textarea.value,
          inDialog: textarea.closest('[role="dialog"]') !== null,
        });
      }
      return execResult;
    }),
  });
  return copiedFrom;
}

/** Creates a user so the temporary password and its Copy button are shown. */
async function renderWithGeneratedPassword() {
  const onSave = vi.fn().mockResolvedValue("temporary-secret");
  render(<CreateUserModal onClose={vi.fn()} onSave={onSave} isLoading={false} error={null} />);
  fireEvent.change(screen.getByPlaceholderText("Enter username"), { target: { value: "alice" } });
  fireEvent.click(screen.getByRole("button", { name: "Create User" }));
  await screen.findByDisplayValue("temporary-secret");
}

describe("CreateUserModal", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    Reflect.deleteProperty(document, "execCommand");
    toastError.mockReset();
  });

  it("shows an inline validation error for an empty username", async () => {
    const onSave = vi.fn();
    render(<CreateUserModal onClose={vi.fn()} onSave={onSave} isLoading={false} error={null} />);

    fireEvent.click(screen.getByRole("button", { name: "Create User" }));

    expect(await screen.findByText("Username is required")).toBeTruthy();
    expect(screen.getByPlaceholderText("Enter username").getAttribute("aria-invalid")).toBe("true");
    expect(onSave).not.toHaveBeenCalled();
  });

  it("normalizes values and displays the generated password", async () => {
    const onSave = vi.fn().mockResolvedValue("temporary-secret");
    render(<CreateUserModal onClose={vi.fn()} onSave={onSave} isLoading={false} error={null} />);

    fireEvent.change(screen.getByPlaceholderText("Enter username"), {
      target: { value: "  alice  " },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter display name (optional)"), {
      target: { value: "  Alice Q.  " },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter organization or affiliation (optional)"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Create default project/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create User" }));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        username: "alice",
        display_name: "Alice Q.",
        organization: undefined,
        create_default_project: true,
      }),
    );
    expect(await screen.findByDisplayValue("temporary-secret")).toBeTruthy();
    expect(screen.getByText("alice")).toBeTruthy();
  });

  it("copies the temporary password over HTTP from inside the modal", async () => {
    const copiedFrom = stubInsecureClipboard(true);
    await renderWithGeneratedPassword();

    const copyButton = screen.getByRole("button", { name: "Copy" });
    copyButton.focus();
    fireEvent.click(copyButton);

    expect(await screen.findByRole("button", { name: "Copied" })).toBeTruthy();
    expect(copiedFrom).toEqual([{ value: "temporary-secret", inDialog: true }]);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("reports a failed copy instead of showing Copied", async () => {
    stubInsecureClipboard(false);
    await renderWithGeneratedPassword();

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Failed to copy password"));
    expect(screen.queryByRole("button", { name: "Copied" })).toBeNull();
  });
});
