import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CopyLinkButton } from "@/components/ui/CopyLinkButton";
import { VisibilityLabel } from "@/components/ui/VisibilityLabel";
import { VisibilitySelector } from "@/components/ui/VisibilitySelector";

const mocks = vi.hoisted(() => ({
  copyText: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock("@/lib/utils/clipboard", () => ({ copyText: mocks.copyText }));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mocks.success, error: mocks.error }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("VisibilityLabel", () => {
  it("names private and project visibility, with custom wording", () => {
    const { rerender } = render(<VisibilityLabel visibility="private" />);
    expect(screen.getByText("Private")).toBeInTheDocument();
    rerender(<VisibilityLabel visibility="project" />);
    expect(screen.getByText("Shared with project")).toBeInTheDocument();
    rerender(<VisibilityLabel visibility="project" projectLabel="Snapshot shared" />);
    expect(screen.getByText("Snapshot shared")).toBeInTheDocument();
  });
});

describe("VisibilitySelector", () => {
  it("reports the chosen visibility and shows its descriptions and hint", () => {
    const onChange = vi.fn();
    render(
      <VisibilitySelector
        value="private"
        onChange={onChange}
        privateDescription="Only you"
        projectDescription="Every member"
        hint="Change it later"
      />,
    );
    expect(screen.getByRole("group", { name: "Sharing" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Private/ })).toBeChecked();
    expect(screen.getByText("Every member")).toBeInTheDocument();
    expect(screen.getByText("Change it later")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Shared with project/ }));
    expect(onChange).toHaveBeenCalledWith("project");
  });

  it("disables both choices", () => {
    render(
      <VisibilitySelector
        value="project"
        onChange={vi.fn()}
        privateDescription="a"
        projectDescription="b"
        disabled
      />,
    );
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
  });
});

describe("CopyLinkButton", () => {
  it("copies the given link and confirms it", async () => {
    mocks.copyText.mockResolvedValue(undefined);
    render(<CopyLinkButton url="https://qdash.example/chat/shared/x?project=p" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    await vi.waitFor(() => expect(mocks.success).toHaveBeenCalledWith("Link copied"));
    expect(mocks.copyText).toHaveBeenCalledWith("https://qdash.example/chat/shared/x?project=p");
  });

  it("copies the current page by default and reports a failure", async () => {
    mocks.copyText.mockRejectedValue(new Error("denied"));
    render(<CopyLinkButton />);
    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    await vi.waitFor(() => expect(mocks.error).toHaveBeenCalledWith("Failed to copy the link"));
    expect(mocks.copyText).toHaveBeenCalledWith(window.location.href);
  });
});
