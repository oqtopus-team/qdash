import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DashboardChipNoteCard } from "@/components/features/dashboard/DashboardChipNoteCard";

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/chip/chip", () => ({
  getGetChipNoteQueryKey: vi.fn(),
  getGetChipQueryKey: vi.fn(),
  getListChipsQueryKey: vi.fn(),
  useDeleteChipNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useGetChipNote: () => ({ data: { data: null }, isLoading: false }),
  useUpsertChipNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));

vi.mock("@/components/ui/MarkdownEditor", () => ({
  MarkdownEditor: () => <div data-testid="markdown-editor" />,
}));

describe("DashboardChipNoteCard", () => {
  it("keeps an empty note compact until the user chooses to edit", () => {
    render(<DashboardChipNoteCard chipId="chip-1" />);

    expect(screen.queryByTestId("markdown-editor")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add note" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add note" }));

    expect(screen.getByTestId("markdown-editor")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByTestId("markdown-editor")).not.toBeInTheDocument();
  });
});
