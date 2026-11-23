import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectProvider, useProject } from "@/contexts/ProjectContext";

const PROJECT_STORAGE_KEY = "qdash_current_project_id";

vi.mock("next/navigation", () => ({
  usePathname: () => "/chip",
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { username: "alice", default_project_id: null },
    accessToken: "token",
  }),
}));

vi.mock("@/client/projects/projects", () => ({
  useListProjects: () => ({
    data: {
      data: {
        projects: [
          { project_id: "project-1", name: "One" },
          { project_id: "project-2", name: "Two" },
        ],
      },
    },
    isLoading: false,
    refetch: vi.fn(),
  }),
  useListProjectMembers: () => ({ data: undefined }),
}));

/** One request of the probe: the project header it carried, answered by the test. */
interface ChipRequest {
  project: string | null;
  resolve: (chips: string) => void;
}

let chipRequests: ChipRequest[] = [];
let projectListRequests = 0;

/** A project-scoped query and a project-independent one, like the app's generated hooks. */
function Probe() {
  const { projectId, switchProject } = useProject();
  const chips = useQuery({
    queryKey: ["/chips"],
    // Like the axios interceptor, the project header is read from storage per request.
    queryFn: () =>
      new Promise<string>((resolve) => {
        chipRequests.push({ project: window.localStorage.getItem(PROJECT_STORAGE_KEY), resolve });
      }),
  });
  const projects = useQuery({
    queryKey: ["/projects", "probe"],
    queryFn: async () => {
      projectListRequests += 1;
      return "projects";
    },
  });
  return (
    <div>
      <p data-testid="project">{projectId ?? "none"}</p>
      <p data-testid="chips">{chips.data ?? "loading"}</p>
      <p data-testid="projects">{projects.data ?? "loading"}</p>
      <button type="button" onClick={() => switchProject("project-2")}>
        Switch
      </button>
    </div>
  );
}

function renderProvider() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ProjectProvider>
        <Probe />
      </ProjectProvider>
    </QueryClientProvider>,
  );
  return client;
}

function answer(project: string, chips: string) {
  const request = chipRequests.filter((item) => item.project === project).pop();
  if (!request) throw new Error(`No request for ${project}`);
  act(() => request.resolve(chips));
}

function query(): URLSearchParams {
  return new URLSearchParams(window.location.search);
}

describe("ProjectProvider project switch", () => {
  beforeEach(() => {
    chipRequests = [];
    projectListRequests = 0;
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-1");
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  it("keeps a deep link's chip and cached answers when it names the stored project", async () => {
    window.history.replaceState(null, "", "/chip?project=project-1&chip=chip-a");
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("project").textContent).toBe("project-1"));
    answer("project-1", "chips of project-1");
    await waitFor(() => expect(screen.getByTestId("chips").textContent).toBe("chips of project-1"));
    expect(chipRequests).toHaveLength(1);
    expect(query().get("chip")).toBe("chip-a");
  });

  it("drops what was fetched for the stored project when a deep link names another", async () => {
    window.history.replaceState(null, "", "/chip?project=project-2&chip=chip-b");
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("project").textContent).toBe("project-2"));
    // Whatever was requested before the provider chose project 2 never reaches the screen.
    for (const request of chipRequests.filter((item) => item.project === "project-1")) {
      act(() => request.resolve("chips of project-1"));
    }
    await waitFor(() =>
      expect(chipRequests.some((item) => item.project === "project-2")).toBe(true),
    );
    answer("project-2", "chips of project-2");
    await waitFor(() => expect(screen.getByTestId("chips").textContent).toBe("chips of project-2"));
    expect(query().get("chip")).toBe("chip-b");
  });

  it("clears the previous project's records from the URL and the cache on an explicit switch", async () => {
    window.history.replaceState(
      null,
      "",
      "/chip?project=project-1&chip=chip-a&cooldown=cd-1&date=20261101&view=2q&task=CheckT1",
    );
    const client = renderProvider();
    await waitFor(() => expect(screen.getByTestId("project").textContent).toBe("project-1"));
    answer("project-1", "chips of project-1");
    await waitFor(() => expect(screen.getByTestId("chips").textContent).toBe("chips of project-1"));
    await waitFor(() => expect(screen.getByTestId("projects").textContent).toBe("projects"));

    // A refetch for project 1 is still on its way when the user switches.
    act(() => {
      void client.invalidateQueries({ queryKey: ["/chips"] });
    });
    const lateProject1 = chipRequests[chipRequests.length - 1];
    expect(lateProject1?.project).toBe("project-1");

    const historyLength = window.history.length;
    act(() => screen.getByRole("button", { name: "Switch" }).click());

    await waitFor(() => expect(screen.getByTestId("project").textContent).toBe("project-2"));
    // Records of project 1 leave the URL; filters that mean the same in every project stay.
    expect(query().get("project")).toBe("project-2");
    expect(query().has("chip")).toBe(false);
    expect(query().has("cooldown")).toBe(false);
    expect(query().get("date")).toBe("20261101");
    expect(query().get("view")).toBe("2q");
    expect(query().get("task")).toBe("CheckT1");
    // A new history entry, so Back can return to project 1.
    expect(window.history.length).toBe(historyLength + 1);

    // Project 1's answer is not shown while project 2 loads, even when it arrives late.
    expect(screen.getByTestId("chips").textContent).toBe("loading");
    act(() => lateProject1?.resolve("late chips of project-1"));
    await act(async () => {});
    expect(screen.getByTestId("chips").textContent).toBe("loading");

    answer("project-2", "chips of project-2");
    await waitFor(() => expect(screen.getByTestId("chips").textContent).toBe("chips of project-2"));
    // Answers that do not depend on the project are kept.
    expect(screen.getByTestId("projects").textContent).toBe("projects");
    expect(projectListRequests).toBe(1);
  });

  it("returns to the previous project and its chip with Back", async () => {
    window.history.replaceState(null, "", "/chip?project=project-1&chip=chip-a");
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("project").textContent).toBe("project-1"));
    answer("project-1", "chips of project-1");

    act(() => screen.getByRole("button", { name: "Switch" }).click());
    await waitFor(() => expect(screen.getByTestId("project").textContent).toBe("project-2"));
    answer("project-2", "chips of project-2");
    await waitFor(() => expect(screen.getByTestId("chips").textContent).toBe("chips of project-2"));

    act(() => window.history.back());
    await waitFor(() => expect(screen.getByTestId("project").textContent).toBe("project-1"));
    expect(query().get("chip")).toBe("chip-a");
    expect(window.localStorage.getItem(PROJECT_STORAGE_KEY)).toBe("project-1");
    // Project 2's list is not shown as project 1's.
    expect(screen.getByTestId("chips").textContent).toBe("loading");
    answer("project-1", "chips of project-1 again");
    await waitFor(() =>
      expect(screen.getByTestId("chips").textContent).toBe("chips of project-1 again"),
    );
  });
});
