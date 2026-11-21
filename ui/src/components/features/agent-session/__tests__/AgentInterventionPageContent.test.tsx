import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

import { AgentInterventionPageContent } from "../AgentInterventionPageContent";
import { interventionActionState, interventionHref } from "../interventionLabels";

let canEdit = true;
const PROJECTS = [{ project_id: "lab-a" }, { project_id: "lab-b" }];
let project: { projectId: string | null; projects: { project_id: string }[]; loading: boolean };
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit, ...project }),
}));
let auth: { accessToken: string | null; loading: boolean } = {
  accessToken: "token",
  loading: false,
};
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));

const BASE = {
  intervention_id: "int-1",
  project_id: "lab-a",
  session_id: "ses-1",
  chip_id: "chip-001",
  idempotency_key: "k",
  created_by: "agent-user",
  reason: "unknown_outcome",
  summary: "CheckRabi evaluation reported LOW_CONTRAST, which has no next action",
  question: "Is the Rabi oscillation usable?",
  node_id: "rabi",
  task_name: "CheckRabi",
  qids: ["Q00"],
  attempts: [
    {
      node_id: "rabi",
      task_name: "CheckRabi",
      qid: "Q00",
      transition: "pass",
      status: "LOW_CONTRAST",
      reason: "Candidate passed and remains staged",
      action_id: "act-1",
      execution_id: "exec-1",
      task_id: "task-1",
      evaluation_id: "ev-1",
      evaluation_run_id: "evr-1",
    },
  ],
  checkpoint: {
    version: 1,
    qid: "Q00",
    nodes: [
      { id: "rabi", task_name: "CheckRabi", candidate_parameter: "control_amplitude" },
      { id: "chevron", task_name: "CheckChevron", candidate_parameter: "qubit_frequency" },
    ],
    idempotency_prefix: "plan-1",
    node_path: ["rabi"],
    visit_counts: { rabi: 1 },
    stopped_node_id: "rabi",
    max_node_executions: 4,
  },
  plan_hash: "sha256:abc",
  pauses_session: true,
  status: "open",
  response: null,
  notification: {
    status: "sent",
    attempts: 1,
    last_error: "",
    sent_at: "2026-11-21T01:00:00Z",
    last_reply_error: "",
  },
  events: [{ at: "2026-11-21T01:00:00Z", actor: "agent-user", kind: "created", detail: "" }],
  created_at: "2026-11-21T01:00:00Z",
  updated_at: "2026-11-21T01:00:00Z",
  session_status: "waiting_for_human",
  session_state_version: 3,
  session_expires_at: "2026-11-21T07:00:00Z",
  actions_used: 1,
  max_actions: 4,
  can_resume: true,
  resume_blockers: [],
  resume_options: [
    {
      node_id: "rabi",
      task_name: "CheckRabi",
      visits: 1,
      max_visits: 2,
      available: true,
      reason: "",
    },
    {
      node_id: "chevron",
      task_name: "CheckChevron",
      visits: 0,
      max_visits: 2,
      available: true,
      reason: "",
    },
  ],
  resume_command: null,
  page_path: "/agent-sessions/ses-1/interventions/int-1",
};

let current: Record<string, unknown>;
let failGet: string | null = null;
const posts: { url: string; body: unknown; project: unknown }[] = [];
const gets: { url: string; project: unknown }[] = [];
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const fakeAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const requestProject = config.headers?.["X-Project-Id"];
  if (config.method === "get") {
    gets.push({ url: config.url ?? "", project: requestProject });
    if (failGet) {
      throw new AxiosError("Request failed", "ERR_BAD_RESPONSE", config, null, {
        data: { detail: failGet },
        status: 500,
        statusText: "Internal Server Error",
        headers: {},
        config,
      });
    }
  }
  if (config.method === "post") {
    const body = typeof config.data === "string" ? JSON.parse(config.data) : config.data;
    posts.push({ url: config.url ?? "", body, project: requestProject });
    if (config.url?.endsWith("/respond")) {
      current = {
        ...current,
        status: "resume_authorized",
        resume_command:
          "qdash-agent --profile PROFILE resume-plan --session-id ses-1 --intervention-id int-1",
        response: {
          response_id: "r",
          decision: "resume",
          guidance: (body as { guidance: string }).guidance,
          resume_node_id: (body as { resume_node_id: string }).resume_node_id,
          responded_by: "expert",
          responded_at: "2026-11-21T02:00:00Z",
          expected_state_version: 3,
        },
      };
    }
    if (config.url?.endsWith("/notification/retry")) {
      current = { ...current, notification: { ...BASE.notification, status: "sent", attempts: 2 } };
    }
  }
  return { data: current, status: 200, statusText: "OK", headers: {}, config };
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page = () => (
    <QueryClientProvider client={client}>
      <AgentInterventionPageContent sessionId="ses-1" interventionId="int-1" />
    </QueryClientProvider>
  );
  const view = render(page());
  return { rerender: () => view.rerender(page()) };
}

function openLink(projectId: string) {
  window.history.replaceState(
    null,
    "",
    `/agent-sessions/ses-1/interventions/int-1?project=${projectId}`,
  );
}

describe("AgentInterventionPageContent", () => {
  beforeEach(() => {
    canEdit = true;
    current = { ...BASE };
    failGet = null;
    project = { projectId: "lab-a", projects: PROJECTS, loading: false };
    openLink("lab-a");
    posts.length = 0;
    gets.length = 0;
    AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  });
  afterEach(() => {
    cleanup();
    AXIOS_INSTANCE.defaults.adapter = originalAdapter;
  });

  it("shows the reason, question, evidence links, and paused state", async () => {
    setup();
    expect(await screen.findByRole("heading", { name: "Unknown outcome" })).toBeTruthy();
    expect(screen.getByText("Is the Rabi oscillation usable?")).toBeTruthy();
    expect(screen.getByText(/The session is paused/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Execution" }).getAttribute("href")).toBe(
      "/executions/exec-1",
    );
    expect(screen.getByRole("link", { name: "Result and figures" }).getAttribute("href")).toBe(
      "/task-results/task-1",
    );
    expect(screen.getByRole("link", { name: "Evaluation" }).getAttribute("href")).toBe(
      "/evaluations/evr-1",
    );
    expect(screen.getByText("Slack sent")).toBeTruthy();
  });

  it("lets an editor authorize a resume from a chosen plan node and then shows the command", async () => {
    setup();
    await screen.findByRole("heading", { name: "Unknown outcome" });
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Weak drive; check frequency" },
    });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "chevron" } });
    fireEvent.click(screen.getByRole("button", { name: "Authorize resume" }));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].url).toBe("/agent-sessions/ses-1/interventions/int-1/respond");
    expect(posts[0].body).toMatchObject({
      expected_state_version: 3,
      decision: "resume",
      guidance: "Weak drive; check frequency",
      resume_node_id: "chevron",
    });
    expect(await screen.findByText(/resume-plan --session-id ses-1/)).toBeTruthy();
    expect(screen.getByText("Resume authorized")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Authorize resume" })).toBeNull();
  });

  it("asks before stopping the session", async () => {
    setup();
    await screen.findByRole("heading", { name: "Unknown outcome" });
    fireEvent.click(screen.getByRole("button", { name: "Stop session" }));
    expect(await screen.findByText("Stop this session?")).toBeTruthy();
    expect(posts).toHaveLength(0);
  });

  it("explains why a resume is not possible and disables it", async () => {
    current = {
      ...BASE,
      can_resume: false,
      resume_blockers: [
        "The session used all 4 of its actions; a newly authorized session is needed",
      ],
    };
    setup();
    expect(await screen.findByText(/a newly authorized session is needed/)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Authorize resume" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Stop session" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("shows a viewer the record without the response form", async () => {
    canEdit = false;
    setup();
    expect(await screen.findByText(/An editor of this project can answer/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Authorize resume" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry Slack" })).toBeNull();
  });

  it("shows a failed Slack delivery and retries it for an editor", async () => {
    current = {
      ...BASE,
      notification: {
        ...BASE.notification,
        status: "failed",
        attempts: 6,
        last_error: "ConnectionError",
      },
    };
    setup();
    expect(await screen.findByText("Slack failed")).toBeTruthy();
    expect(screen.getByText(/ConnectionError/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry Slack" }));
    await waitFor(() =>
      expect(posts[0]?.url).toBe("/agent-sessions/ses-1/interventions/int-1/notification/retry"),
    );
    expect(await screen.findByText("Slack sent")).toBeTruthy();
  });
});

describe("AgentInterventionPageContent project link", () => {
  beforeEach(() => {
    auth = { accessToken: "token", loading: false };
    canEdit = true;
    current = { ...BASE };
    failGet = null;
    posts.length = 0;
    gets.length = 0;
    AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  });
  afterEach(() => {
    cleanup();
    AXIOS_INSTANCE.defaults.adapter = originalAdapter;
  });

  it("waits for the linked project before loading, then asks only that project", async () => {
    // The browser still has another project selected when the Slack link opens.
    openLink("lab-a");
    project = { projectId: "lab-b", projects: PROJECTS, loading: false };
    const { rerender } = setup();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(gets).toHaveLength(0);
    expect(screen.queryByRole("heading", { name: "Unknown outcome" })).toBeNull();

    project = { ...project, projectId: "lab-a" };
    rerender();
    expect(await screen.findByRole("heading", { name: "Unknown outcome" })).toBeTruthy();
    expect(gets.length).toBeGreaterThan(0);
    expect(gets.every((request) => request.project === "lab-a")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Authorize resume" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].project).toBe("lab-a");
  });

  it("reports a linked project the user cannot open and never asks another project", async () => {
    openLink("lab-z");
    // The provider falls back to another accessible project.
    project = { projectId: "lab-b", projects: PROJECTS, loading: false };
    setup();
    expect(await screen.findByText(/belongs to project lab-z/)).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(gets).toHaveLength(0);
  });

  it("reports a linked project to a user with no project and asks nothing", async () => {
    openLink("lab-a");
    project = { projectId: null, projects: [], loading: false };
    setup();
    expect(await screen.findByText(/belongs to project lab-a/)).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(gets).toHaveLength(0);
  });

  it("reports a user with no project when the page has no project link", async () => {
    window.history.replaceState(null, "", "/agent-sessions/ses-1/interventions/int-1");
    project = { projectId: null, projects: [], loading: false };
    setup();
    expect(await screen.findByText(/Your account has no project/)).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(gets).toHaveLength(0);
  });

  it("keeps waiting while the project list cannot have loaded yet", async () => {
    openLink("lab-a");
    auth = { accessToken: null, loading: true };
    project = { projectId: null, projects: [], loading: false };
    setup();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(gets).toHaveLength(0);
  });

  it("shows a server failure for the linked project", async () => {
    openLink("lab-a");
    project = { projectId: "lab-a", projects: PROJECTS, loading: false };
    failGet = "The intervention store is unavailable";
    setup();
    expect(await screen.findByText("The intervention store is unavailable")).toBeTruthy();
    expect(gets.every((request) => request.project === "lab-a")).toBe(true);
  });
});

describe("interventionLabels", () => {
  it("links to the intervention with its project selected", () => {
    expect(interventionHref(BASE as never)).toBe(
      "/agent-sessions/ses-1/interventions/int-1?project=lab-a",
    );
  });

  it("offers an answer only while open", () => {
    expect(interventionActionState(BASE as never)).toEqual({ kind: "answer", canResume: true });
    expect(interventionActionState({ ...BASE, status: "resume_authorized" } as never)).toEqual({
      kind: "ready_to_resume",
    });
    expect(interventionActionState({ ...BASE, status: "stopped" } as never)).toEqual({
      kind: "closed",
    });
  });
});
