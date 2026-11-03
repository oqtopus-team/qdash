import type {
  ContextMenuOpenContext,
  FileTree as FileTreeModel,
  FileTreeDropTarget,
} from "@pierre/trees";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FlowExplorer } from "@/components/features/flow/FlowExplorer";
import type { PierreFileTree } from "@/components/ui/PierreFileTree";
import type { FlowSummary } from "@/schemas";

type TreeProps = React.ComponentProps<typeof PierreFileTree>;
type TreeNode = TreeProps["nodes"][number];

const mockMoveFlow = vi.hoisted(() => vi.fn());
const mockInvalidate = vi.hoisted(() => vi.fn());
const mockToast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
/** The props the last render handed to the (mocked) tree. */
const treeProps = vi.hoisted(() => ({ current: null as TreeProps | null }));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidate }),
  useMutation: (options: {
    mutationFn: (vars: unknown) => Promise<unknown>;
    onSuccess?: (result: unknown) => void;
    onError?: (error: unknown) => void;
  }) => ({
    isPending: false,
    mutate: (vars: unknown) =>
      options
        .mutationFn(vars)
        .then((result) => options.onSuccess?.(result))
        .catch((error: unknown) => options.onError?.(error)),
  }),
}));
vi.mock("@/client/flow/flow", () => ({
  getListFlowsQueryKey: () => ["/flows"],
  moveFlow: (...args: unknown[]) => mockMoveFlow(...args),
}));
vi.mock("@/components/ui/Toast/useToast", () => ({ useToast: () => mockToast }));
vi.mock("@/components/ui/PierreFileTree", () => ({
  PierreFileTree: (props: TreeProps) => {
    treeProps.current = props;
    return <div data-testid="tree" />;
  },
}));

function flow(name: string, created_by: string, folder = ""): FlowSummary {
  return {
    name,
    created_by,
    description: "",
    chip_id: "chip1",
    flow_function_name: "main",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
    tags: [],
    folder,
  };
}

const flows = [
  flow("root_flow", "mia"),
  flow("daily_a", "mia", "daily"),
  flow("daily_t1", "mia", "daily/t1"),
  flow("zoe_flow", "zoe", "zoes"),
];

function renderExplorer(overrides: Partial<React.ComponentProps<typeof FlowExplorer>> = {}) {
  return render(
    <FlowExplorer
      flows={flows}
      username="mia"
      currentName="daily_a"
      isDirty
      filter=""
      onOpen={vi.fn()}
      {...overrides}
    />,
  );
}

/** The tree's props with the optional callbacks the explorer always passes. */
function tree() {
  const props = treeProps.current;
  if (!props?.dragAndDrop || !props.renaming || !props.renderContextMenu) {
    throw new Error("the explorer did not render the tree with its callbacks");
  }
  return {
    ...props,
    dnd: props.dragAndDrop,
    renaming: props.renaming,
    menu: props.renderContextMenu,
  };
}
const paths = (nodes: TreeNode[] | null | undefined) => (nodes ?? []).map((n) => n.path);
const children = (node: TreeNode | undefined) => node?.children ?? [];
const target = (directoryPath: string | null): FileTreeDropTarget => ({
  directoryPath,
  flattenedSegmentPath: null,
  hoveredPath: directoryPath,
  kind: directoryPath === null ? "root" : "directory",
});
const menuContext = { close: vi.fn() } as unknown as ContextMenuOpenContext;
const menuModel = { add: vi.fn(), startRenaming: vi.fn() } as unknown as FileTreeModel;

beforeEach(() => {
  treeProps.current = null;
  mockMoveFlow.mockReset();
  mockMoveFlow.mockImplementation((name: string, body: { folder: string }) =>
    Promise.resolve({ data: { name, folder: body.folder, message: "ok" } }),
  );
  mockInvalidate.mockReset();
  mockToast.success.mockReset();
  mockToast.error.mockReset();
});
afterEach(() => cleanup());

describe("FlowExplorer", () => {
  it("shows the open flow's space as folder/name.py, selected and decorated", () => {
    renderExplorer();
    const props = tree();
    expect(paths(props.nodes)).toEqual(["daily", "root_flow.py"]);
    const dailyA = children(props.nodes[0]).find((n) => n.path === "daily/daily_a.py");
    expect(dailyA?.decoration?.title).toBe("Unsaved changes");
    expect(props.selectedPath).toBe("daily/daily_a.py");
    expect(props.flattenEmptyDirectories).toBe(false);
    // The space selector lists the signed-in user first, marked.
    const select = screen.getByLabelText("Space") as HTMLSelectElement;
    expect(select.value).toBe("mia");
    expect([...select.options].map((o) => o.textContent)).toEqual(["mia (you)", "zoe"]);
  });

  it("switches to another creator's space, which can be requested when the page opens", () => {
    renderExplorer({ initialSpace: "zoe" });
    expect(paths(tree().nodes)).toEqual(["zoes"]);
    // The open flow belongs to another space, so nothing is selected here.
    expect(tree().selectedPath).toBeNull();
    fireEvent.change(screen.getByLabelText("Space"), { target: { value: "mia" } });
    expect(paths(tree().nodes)).toEqual(["daily", "root_flow.py"]);
    cleanup();
    // A space the list does not know falls back to the open flow's.
    renderExplorer({ initialSpace: "nobody" });
    expect(paths(tree().nodes)).toEqual(["daily", "root_flow.py"]);
  });

  it("opens the flow of a selected file and filters by name", () => {
    const onOpen = vi.fn();
    renderExplorer({ onOpen, filter: "t1" });
    tree().onSelectFile("daily/t1/daily_t1.py");
    expect(onOpen).toHaveBeenCalledWith("daily_t1");
    expect(paths(children(tree().nodes[0]))).toEqual(["daily/t1"]);
    cleanup();
    renderExplorer({ filter: "nothing" });
    expect(screen.getByText("No flows match the filter.")).toBeInTheDocument();
  });

  it("re-files dropped rows through the move API and reloads the list", async () => {
    renderExplorer();
    const { dnd } = tree();
    expect(dnd.canDrop?.({ draggedPaths: ["root_flow.py"], target: target("daily") })).toBe(true);
    expect(
      dnd.canDrop?.({ draggedPaths: ["root_flow.py"], target: target("daily/daily_a.py") }),
    ).toBe(false);
    // A folder dropped on its own parent is a no-op.
    dnd.onDropComplete?.({ draggedPaths: ["daily"], target: target(null), operation: "move" });
    expect(mockMoveFlow).not.toHaveBeenCalled();
    dnd.onDropComplete?.({
      draggedPaths: ["root_flow.py", "daily/t1"],
      target: target("daily"),
      operation: "batch",
    });
    await waitFor(() => expect(mockMoveFlow).toHaveBeenCalledTimes(1));
    expect(mockMoveFlow).toHaveBeenCalledWith("root_flow", { folder: "daily" });
    await waitFor(() => expect(mockInvalidate).toHaveBeenCalledWith({ queryKey: ["/flows"] }));
    expect(mockToast.success).toHaveBeenCalledWith("Moved root_flow to daily");
    // Dropping on the empty area moves to the top of the space.
    dnd.onDropComplete?.({
      draggedPaths: ["daily/t1/daily_t1.py"],
      target: target(null),
      operation: "move",
    });
    await waitFor(() => expect(mockMoveFlow).toHaveBeenCalledWith("daily_t1", { folder: "" }));
  });

  it("renames a folder by moving everything under it, and keeps an empty folder locally", async () => {
    renderExplorer();
    const { renaming } = tree();
    expect(renaming.canRename?.({ isFolder: false, path: "root_flow.py" })).toBe(false);
    expect(renaming.canRename?.({ isFolder: true, path: "daily" })).toBe(true);

    renaming.onRename?.({ sourcePath: "daily", destinationPath: "nightly", isFolder: true });
    await waitFor(() => expect(mockMoveFlow).toHaveBeenCalledTimes(2));
    expect(mockMoveFlow).toHaveBeenCalledWith("daily_a", { folder: "nightly" });
    expect(mockMoveFlow).toHaveBeenCalledWith("daily_t1", { folder: "nightly/t1" });
    expect(mockToast.success).toHaveBeenCalledWith("Moved 2 workflows");

    // A placeholder folder named in place holds no flow: it is kept on the page only.
    mockMoveFlow.mockClear();
    tree().renaming.onRename?.({
      sourcePath: "new_folder",
      destinationPath: "weekly",
      isFolder: true,
    });
    await waitFor(() => expect(paths(tree().nodes)).toContain("weekly"));
    expect(mockMoveFlow).not.toHaveBeenCalled();

    // A name the API would refuse is reported and the tree reset instead.
    const before = tree().resetToken;
    tree().renaming.onRename?.({
      sourcePath: "weekly",
      destinationPath: "bad name",
      isFolder: true,
    });
    expect(mockToast.error).toHaveBeenCalledWith(
      "Folder names use letters, numbers and underscores",
    );
    await waitFor(() => expect(tree().resetToken).toBe((before ?? 0) + 1));
  });

  it("adds an empty top-level folder from the header button", async () => {
    renderExplorer();
    fireEvent.click(screen.getByRole("button", { name: "New folder" }));
    await waitFor(() => expect(paths(tree().nodes)).toContain("new_folder"));
    fireEvent.click(screen.getByRole("button", { name: "New folder" }));
    await waitFor(() => expect(paths(tree().nodes)).toContain("new_folder_2"));
  });

  it("reports a failed move, reloads and resets the tree", async () => {
    mockMoveFlow.mockImplementation(() =>
      Promise.reject({ response: { data: { detail: "Editor role required" } } }),
    );
    renderExplorer();
    const before = tree().resetToken ?? 0;
    tree().dnd.onDropComplete?.({
      draggedPaths: ["root_flow.py"],
      target: target("daily"),
      operation: "move",
    });
    await waitFor(() =>
      expect(mockToast.error).toHaveBeenCalledWith("Could not move: Editor role required"),
    );
    expect(mockInvalidate).toHaveBeenCalled();
    await waitFor(() => expect(tree().resetToken).toBe(before + 1));
  });

  it("offers the space's folders in a file's context menu", async () => {
    renderExplorer({ currentName: "root_flow", isDirty: false });
    const menu = tree().menu(
      { kind: "file", name: "root_flow.py", path: "root_flow.py" },
      menuContext,
      menuModel,
    );
    cleanup();
    render(<>{menu}</>);
    expect(screen.getByRole("button", { name: "Top of the space" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "daily/t1" }));
    await waitFor(() =>
      expect(mockMoveFlow).toHaveBeenCalledWith("root_flow", { folder: "daily/t1" }),
    );
  });

  it("lets a folder's context menu start a placeholder rename or rename the folder", () => {
    renderExplorer();
    const add = vi.fn();
    const startRenaming = vi.fn();
    const close = vi.fn();
    const model = { add, startRenaming } as unknown as FileTreeModel;
    const context = { close } as unknown as ContextMenuOpenContext;
    const menu = tree().menu({ kind: "directory", name: "daily", path: "daily" }, context, model);
    cleanup();
    render(<>{menu}</>);
    fireEvent.click(screen.getByRole("button", { name: "New folder" }));
    expect(add).toHaveBeenCalledWith("daily/new_folder/");
    expect(startRenaming).toHaveBeenCalledWith("daily/new_folder", { removeIfCanceled: true });
    fireEvent.click(screen.getByRole("button", { name: "Rename folder" }));
    expect(startRenaming).toHaveBeenCalledWith("daily");
    expect(close).toHaveBeenCalled();
  });
});
