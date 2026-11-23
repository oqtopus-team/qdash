import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

import { AgentSessionPageContent } from "../AgentSessionPageContent";
import {
  auditKindLabel,
  auditProvenanceLabel,
  gateOutcomeLabel,
} from "../AgentSessionAuditTimeline";

const PROJECTS = [{ project_id: "lab-a" }, { project_id: "lab-b" }];
let project: { projectId: string | null; projects: { project_id: string }[]; loading: boolean };
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: false, ...project }),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ accessToken: "token", loading: false }),
}));

const SESSION = {
  session_id: "ses-1",
  project_id: "lab-a",
  chip_id: "chip-001",
  created_by: "alice",
  policy: {
    qids: ["Q00"],
    allowed_tasks: ["CheckRabi"],
    max_actions: 6,
    autonomy: "auto",
  },
  skill_name: "",
  skill_version: "",
  skill_hash: "",
  model_name: "",
  status: "active",
  state_version: 3,
  action_count: 2,
  created_at: "2026-11-21T01:00:00Z",
  updated_at: "2026-11-21T01:00:00Z",
  expires_at: "2026-11-21T07:00:00Z",
};

function event(sequence: number, fields: Record<string, unknown>) {
  return {
    event_id: `e-${sequence}`,
    sequence,
    at: `2026-11-21T01:0${sequence}:00Z`,
    state_version: sequence,
    kind: "action_proposed",
    summary: `event ${sequence}`,
    actor: "alice",
    actor_kind: "agent",
    provenance: "server_record",
    status: null,
    status_is_current: false,
    missing: [],
    data: {},
    ...fields,
  };
}

const EVENTS = [
  event(0, { kind: "session_created", summary: "alice approved a session", actor_kind: "human" }),
  event(1, {
    kind: "measurement",
    summary: "CheckRabi on Q00: completed",
    execution_id: "exec-1",
    task_id: "task-1",
    status: "completed",
    status_is_current: true,
    missing: ["decision"],
    data: {
      requested_overrides: { qubit_frequency: 7.45 },
      outputs: { control_amplitude: { value: 0.05 } },
      quality_metrics: { r2: 0.98 },
      gate: [{ parameter_name: "control_amplitude", accepted: true }],
    },
  }),
  event(2, {
    kind: "decision",
    provenance: "agent_reported",
    summary: "Assessed pass; next next_task",
    model: { provider: "vllm", model_id: "qwen3:32b", host: "qdash-web-agent" },
    data: { interpretation: "R2 0.98 passes the criterion." },
  }),
];

const PI_MODEL = { provider: "ollama", model_id: "qwen3:32b", host: "pi" };
/** The audit header's identity fields: absent in a session that recorded no model. */
let header: Record<string, unknown> = { missing: ["model"] };

const audits: { cursor: unknown; project: unknown }[] = [];
let exported = 0;
let failAudit: string | null = null;
/** The snapshot the server reads now; a cursor of another snapshot is refused with 409. */
let snapshot = "snap-1";
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const respond = (config: InternalAxiosRequestConfig, data: unknown) => ({
  data,
  status: 200,
  statusText: "OK",
  headers: {},
  config,
});

const fakeAdapter: AxiosAdapter = async (config) => {
  const url = config.url ?? "";
  if (url.endsWith("/audit") || url.endsWith("/audit/export")) {
    if (failAudit) {
      throw new AxiosError("Request failed", "ERR_BAD_RESPONSE", config, null, {
        data: { detail: failAudit },
        status: 403,
        statusText: "Forbidden",
        headers: {},
        config,
      });
    }
  }
  if (url.endsWith("/audit/export")) {
    exported += 1;
    return respond(config, {
      schema_version: "qdash.agent-session-audit.v1",
      snapshot_id: snapshot,
      session: { ...SESSION, missing: [] },
      events: EVENTS,
      total_events: 3,
      complete: true,
    });
  }
  if (url.endsWith("/audit")) {
    const cursor = config.params?.cursor;
    audits.push({ cursor, project: config.headers?.["X-Project-Id"] });
    if (cursor && cursor !== `${snapshot}:2`) {
      throw new AxiosError("Request failed", "ERR_BAD_REQUEST", config, null, {
        data: { detail: "The session's audit changed after its first page was read" },
        status: 409,
        statusText: "Conflict",
        headers: {},
        config,
      });
    }
    const page = cursor ? EVENTS.slice(2) : EVENTS.slice(0, 2);
    return respond(config, {
      schema_version: "qdash.agent-session-audit.v1",
      generated_at: "2026-11-21T02:00:00Z",
      snapshot_id: snapshot,
      session: { ...SESSION, ...header },
      events: page,
      total_events: 3,
      next_cursor: cursor ? null : `${snapshot}:2`,
      complete: Boolean(cursor),
      notes: [],
    });
  }
  if (url.endsWith("/interventions")) return respond(config, { items: [], total: 0 });
  return respond(config, SESSION);
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AgentSessionPageContent sessionId="ses-1" />
    </QueryClientProvider>,
  );
}

describe("AgentSessionAuditTimeline", () => {
  beforeEach(() => {
    project = { projectId: "lab-a", projects: PROJECTS, loading: false };
    window.history.replaceState(null, "", "/agent-sessions/ses-1?project=lab-a");
    audits.length = 0;
    exported = 0;
    failAudit = null;
    snapshot = "snap-1";
    header = { missing: ["model"] };
    AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    AXIOS_INSTANCE.defaults.adapter = originalAdapter;
  });

  it("labels each event's source, shows missing facts, and loads the rest on request", async () => {
    setup();
    expect(await screen.findByText("CheckRabi on Q00: completed")).toBeTruthy();
    expect(screen.getByText(/Showing 2 of 3 events as read at/)).toBeTruthy();
    expect(screen.getByText("Not recorded: decision")).toBeTruthy();
    // A session without a reported model says so and names none.
    expect(screen.getByText("The session did not record: model.")).toBeTruthy();
    expect(screen.queryByText(/Created with model/)).toBeNull();
    expect(screen.getByText("control_amplitude 0.05")).toBeTruthy();
    expect(screen.getByText("control_amplitude accepted")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Result and figures" }).getAttribute("href")).toBe(
      "/task-results/task-1",
    );
    expect(audits).toEqual([{ cursor: undefined, project: "lab-a" }]);

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("R2 0.98 passes the criterion.")).toBeTruthy();
    expect(screen.getByText("Agent statement")).toBeTruthy();
    // Each event names the model its own record reported, and who reported it.
    const model = screen.getByText("model vllm/qwen3:32b");
    expect(model.getAttribute("title")).toBe(
      "Reported by qdash-web-agent; QDash does not verify it",
    );
    expect(screen.getAllByText(/^model /)).toHaveLength(1);
    expect(screen.getByText(/Showing 3 of 3 events/)).toBeTruthy();
    expect(screen.getByText("End of the timeline")).toBeTruthy();
    expect(audits[audits.length - 1]).toEqual({ cursor: "snap-1:2", project: "lab-a" });
  });

  it("shows the model the creating host reported, labelled as not verified", async () => {
    header = { model: PI_MODEL, model_name: "ollama/qwen3:32b", missing: [] };
    setup();
    expect(
      await screen.findByText(
        /Created with model ollama\/qwen3:32b, reported by pi and not verified by QDash/,
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/The session did not record/)).toBeNull();
  });

  it("never joins pages of two snapshots and reads the audit again on request", async () => {
    setup();
    expect(await screen.findByText("CheckRabi on Q00: completed")).toBeTruthy();
    // A new record lands after the first page was read.
    snapshot = "snap-2";
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText(/The audit changed while it was being read/)).toBeTruthy();
    expect(screen.queryByText("R2 0.98 passes the criterion.")).toBeNull();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
    expect(screen.queryByText("End of the timeline")).toBeNull();
    expect(screen.getByText(/Showing 2 of 3 events/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Read again from the start" }));
    await waitFor(() =>
      expect(screen.queryByText(/The audit changed while it was being read/)).toBeNull(),
    );
    expect(audits[audits.length - 1]).toEqual({ cursor: undefined, project: "lab-a" });
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByText("R2 0.98 passes the criterion.")).toBeTruthy();
    expect(audits[audits.length - 1]).toEqual({ cursor: "snap-2:2", project: "lab-a" });
  });

  it("says when the export is a newer read than the timeline shown", async () => {
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: vi.fn(() => "blob:audit"), revokeObjectURL: vi.fn() }),
    );
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    setup();
    expect(await screen.findByText("CheckRabi on Q00: completed")).toBeTruthy();
    snapshot = "snap-2";
    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(await screen.findByText(/The exported file is a newer read of the audit/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() =>
      expect(screen.queryByText(/The exported file is a newer read of the audit/)).toBeNull(),
    );
    expect(audits.filter((entry) => entry.cursor === undefined)).toHaveLength(2);
    click.mockRestore();
  });

  it("exports the whole timeline as one JSON file", async () => {
    const createObjectURL = vi.fn((_blob: Blob) => "blob:audit");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Export JSON" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(exported).toBe(1);
    const blob = createObjectURL.mock.calls[0]![0];
    const body = JSON.parse(await blob.text());
    expect(body.complete).toBe(true);
    expect(body.events).toHaveLength(3);
    click.mockRestore();
  });

  it("reports a refused read instead of an empty timeline", async () => {
    failAudit = "Not a member of this project";
    setup();
    expect(await screen.findByText("Not a member of this project")).toBeTruthy();
    expect(screen.queryByText("End of the timeline")).toBeNull();
  });

  it("sends no audit request for a project the user cannot open", async () => {
    window.history.replaceState(null, "", "/agent-sessions/ses-1?project=lab-z");
    setup();
    expect(await screen.findByText(/which your account cannot\s+open/)).toBeTruthy();
    expect(audits).toEqual([]);
  });

  it("names kinds and sources in plain words", () => {
    expect(auditKindLabel("intervention_response")).toBe("Expert answered");
    expect(auditProvenanceLabel("server_record")).toBe("QDash record");
    expect(auditKindLabel("future_kind")).toBe("future_kind");
  });

  it("tells an out-of-scope output apart from a failed gate", () => {
    expect(gateOutcomeLabel({ accepted: true, rejection: null })).toBe("accepted");
    expect(gateOutcomeLabel({ accepted: false, rejection: "not_in_scope" })).toBe(
      "not in session scope (reference only)",
    );
    expect(gateOutcomeLabel({ accepted: false, rejection: "outside_bounds" })).toBe(
      "rejected: outside bounds",
    );
    expect(gateOutcomeLabel({ accepted: false, rejection: "quality_gate" })).toBe(
      "rejected: quality gate",
    );
    // An audit recorded before the code existed keeps its plain wording.
    expect(gateOutcomeLabel({ accepted: false })).toBe("rejected");
  });
});
