import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPageContent } from "@/components/features/auth/LoginPageContent";

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  setTheme: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ login: mocks.login, loading: false }),
}));

vi.mock("@/contexts/ThemeContext", () => ({
  useTheme: () => ({ theme: "light", setTheme: mocks.setTheme }),
}));

vi.mock("@/components/ui/EnvironmentBadge", () => ({
  EnvironmentBadge: () => null,
}));

vi.mock("next/image", () => ({
  default: ({ alt }: { alt: string }) => <span role="img" aria-label={alt} />,
}));

const originalLocation = window.location;

/** Fills the login form fields with the given values. */
function fillForm(username: string, password: string) {
  fireEvent.change(screen.getByLabelText("User ID"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

/** Clicks the sign-in submit button. */
function submitForm() {
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPageContent", () => {
  beforeEach(() => {
    mocks.login.mockReset();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "/login", search: "", pathname: "/login" },
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  });

  it("shows required errors and does not log in when submitted empty", async () => {
    render(<LoginPageContent />);
    submitForm();

    expect(await screen.findByText("User ID is required")).toBeTruthy();
    expect(screen.getByText("Password is required")).toBeTruthy();

    const username = screen.getByLabelText("User ID");
    const password = screen.getByLabelText("Password");
    expect(username.getAttribute("aria-invalid")).toBe("true");
    expect(username.getAttribute("aria-describedby")).toBe("userName-error");
    expect(password.getAttribute("aria-invalid")).toBe("true");
    expect(password.getAttribute("aria-describedby")).toBe("password-error");
    expect(mocks.login).not.toHaveBeenCalled();
  });

  it("treats a whitespace-only user ID as missing", async () => {
    render(<LoginPageContent />);
    fillForm("   ", "secret");
    submitForm();

    expect(await screen.findByText("User ID is required")).toBeTruthy();
    expect(mocks.login).not.toHaveBeenCalled();
  });

  it("trims the user ID but passes the password through untrimmed", async () => {
    mocks.login.mockResolvedValue(undefined);
    render(<LoginPageContent />);
    fillForm("  alice  ", "  pass word  ");
    submitForm();

    await waitFor(() => expect(mocks.login).toHaveBeenCalledWith("alice", "  pass word  "));
  });

  it("redirects to /execution after a successful login", async () => {
    mocks.login.mockResolvedValue(undefined);
    render(<LoginPageContent />);
    fillForm("alice", "secret");
    submitForm();

    await waitFor(() => expect(window.location.href).toBe("/execution"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a submission error without marking fields invalid when login fails", async () => {
    mocks.login.mockRejectedValue(new Error("unauthorized"));
    render(<LoginPageContent />);
    fillForm("alice", "wrong");
    submitForm();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Login failed. Please check your user ID and password.");
    expect(window.location.href).toBe("/login");

    const username = screen.getByLabelText("User ID");
    const password = screen.getByLabelText("Password");
    expect(username.getAttribute("aria-invalid")).toBe("false");
    expect(password.getAttribute("aria-invalid")).toBe("false");
    expect(password.getAttribute("aria-describedby")).toBe("login-error");
  });

  it("clears a field error once the field is corrected", async () => {
    render(<LoginPageContent />);
    submitForm();
    expect(await screen.findByText("User ID is required")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("User ID"), { target: { value: "alice" } });

    await waitFor(() => expect(screen.queryByText("User ID is required")).toBeNull());
    expect(screen.getByLabelText("User ID").getAttribute("aria-invalid")).toBe("false");
    expect(screen.getByText("Password is required")).toBeTruthy();
  });

  it("clears a stale login error when a later submit fails validation", async () => {
    mocks.login.mockRejectedValue(new Error("unauthorized"));
    render(<LoginPageContent />);
    fillForm("alice", "wrong");
    submitForm();
    expect(await screen.findByRole("alert")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("User ID"), { target: { value: "" } });
    submitForm();

    expect(await screen.findByText("User ID is required")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByLabelText("Password").getAttribute("aria-describedby")).toBeNull();
  });
});
