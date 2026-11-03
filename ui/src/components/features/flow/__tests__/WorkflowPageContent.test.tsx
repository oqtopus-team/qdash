import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowPageContent } from "@/components/features/flow/WorkflowPageContent";

function flow(name: string, created_by: string, folder = "", tags: string[] = []) {
  return {
    name,
    created_by,
    description: "",
    chip_id: "chip1",
    flow_function_name: "main",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
    tags,
    folder,
  };
}

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({
    isLoading: false,
    error: null,
    data: {
      data: {
        flows: [
          flow("zoe_flow", "zoe"),
          flow("my_flow", "mia", "", ["t1"]),
          flow("daily_flow", "mia", "daily/t1"),
        ],
      },
    },
  }),
}));

vi.mock("@/client/flow/flow", () => ({ listFlows: vi.fn() }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ username: "mia" }) }));
vi.mock("@/components/features/flow/FlowSchedulesSection", () => ({
  FlowSchedulesSection: () => <div data-testid="schedules" />,
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: React.ComponentProps<"a">) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

afterEach(() => cleanup());

describe("WorkflowPageContent", () => {
  it("shows one folder per creator, the signed-in user's first and the only one open", () => {
    render(<WorkflowPageContent />);
    const folders = screen.getAllByTestId(/^flow-folder-/);
    expect(folders.map((el) => el.getAttribute("data-testid"))).toEqual([
      "flow-folder-mia",
      "flow-folder-zoe",
    ]);
    expect(folders[0]).toHaveAttribute("open");
    expect(folders[1]).not.toHaveAttribute("open");

    const mine = within(folders[0]!);
    expect(mine.getByText("You")).toBeInTheDocument();
    expect(mine.getByText("2 workflows")).toBeInTheDocument();
    expect(mine.getAllByRole("link", { name: /my_flow/ })[0]).toHaveAttribute(
      "href",
      "/workflow/my_flow",
    );
    expect(mine.queryByText("zoe_flow")).toBeNull();
    expect(within(folders[1]!).queryByText("You")).toBeNull();
    // Each space opens in the editor's Explorer through its first flow.
    expect(within(folders[1]!).getByRole("link", { name: /Open in editor/ })).toHaveAttribute(
      "href",
      "/workflow/zoe_flow?space=zoe",
    );
    // The subfolder path becomes nested, open disclosures with their own counts.
    const daily = mine.getByTestId("flow-subfolder-daily");
    expect(daily).toHaveAttribute("open");
    expect(within(daily).getByTestId("flow-subfolder-daily/t1")).toHaveAttribute("open");
    expect(within(daily).getAllByRole("link", { name: /daily_flow/ }).length).toBeGreaterThan(0);
  });
});
