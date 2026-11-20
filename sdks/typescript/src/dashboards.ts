/**
 * Metric scripts and custom dashboards, defined locally and saved through a
 * session, modelled on the Python `qdash.sdk.dashboard`.
 *
 * A `Script` is the text of a metric script with its name and settings; a
 * `Dashboard` is a list of panels. Building either sends no request and never
 * runs the source: the server validates a script when it is saved and returns
 * its metric catalog. `qdash.scripts` saves scripts and returns a
 * `SavedScript` bound to the saved revision, whose `metric(id)` gives the
 * `ScriptMetric` a dashboard panel pins; `qdash.dashboards` saves dashboards.
 * Every create and update names its target explicitly: nothing is matched by
 * name, cached locally, retried or rolled back.
 */
import { readFile } from "node:fs/promises";
import { basename, extname } from "node:path";

import type { QDashClient } from "@oqtopus-team/qdash-client";
import type {
  AbsolutePeriod,
  CustomDashboardCreateRequest,
  CustomDashboardResponse,
  CustomDashboardUpdateRequest,
  DashboardPanelModel,
  MetricInfo,
  MetricScriptCreateRequest,
  MetricScriptPanelConfig,
  MetricScriptResponse,
  MetricScriptRevision,
  MetricScriptSummary,
  MetricScriptUpdateRequest,
  MetricScriptValidateResponse,
  PanelLayoutModel,
  RelativePeriod,
} from "@oqtopus-team/qdash-client/models";

export type Visibility = "private" | "project";
export type ParamValue = boolean | number | string;
/** A number of days back from evaluation time, or a period object. */
export type PeriodInput = number | RelativePeriod | AbsolutePeriod;

// Pair distances the API knows; a metric's declared hops are limited to these.
const KNOWN_HOPS = [1, 2];
// Default panel sizes on the 12-column grid, as the dashboard editor uses them.
const PANEL_SIZES: Record<string, { w: number; h: number }> = {
  metric_script: { w: 6, h: 4 },
  markdown: { w: 12, h: 2 },
};
const MAX_PANEL_ID = 64;

/**
 * A saved script revision cannot back a panel: it is invalid or lacks the
 * metric. `scriptId` and `revision` name what was saved.
 */
export class MetricScriptError extends Error {
  constructor(
    message: string,
    readonly scriptId: string,
    readonly revision: number | null,
    readonly diagnostics: string[] = [],
  ) {
    super(message);
    this.name = "MetricScriptError";
  }
}

export interface ScriptOptions {
  name: string;
  source: string;
  /** Not sent when undefined: a new script gets "", an update keeps the stored value. */
  description?: string;
  /** Not sent when undefined: a new script is private, an update keeps the stored value. */
  visibility?: Visibility;
}

/** A metric script to save: its name, source text and optional settings. */
export class Script {
  readonly name: string;
  readonly source: string;
  readonly description?: string;
  readonly visibility?: Visibility;

  constructor(options: ScriptOptions) {
    this.name = options.name;
    this.source = options.source;
    if (options.description !== undefined) this.description = options.description;
    if (options.visibility !== undefined) this.visibility = options.visibility;
  }

  /**
   * Read the source text of `path` as UTF-8; the name defaults to the file's
   * base name without extension. The file is never imported or executed.
   */
  static async fromFile(path: string, options: Partial<Omit<ScriptOptions, "source">> = {}): Promise<Script> {
    const source = await readFile(path, "utf8");
    return new Script({ ...options, name: options.name ?? basename(path, extname(path)), source });
  }

  private fields(): MetricScriptCreateRequest {
    return {
      name: this.name,
      source: this.source,
      ...(this.description !== undefined ? { description: this.description } : {}),
      ...(this.visibility !== undefined ? { visibility: this.visibility } : {}),
    };
  }

  /** The `POST /metric-scripts` body. */
  createRequest(): MetricScriptCreateRequest {
    return this.fields();
  }

  /** The `PATCH /metric-scripts/{id}` body; unchanged source adds no revision. */
  updateRequest(expectedRevision?: number): MetricScriptUpdateRequest {
    return { ...this.fields(), ...(expectedRevision !== undefined ? { expected_revision: expectedRevision } : {}) };
  }
}

/** One metric of a saved, validated script revision, as its catalog declares it. */
export class ScriptMetric {
  constructor(
    readonly scriptId: string,
    readonly revision: number,
    readonly info: MetricInfo,
  ) {}

  get id(): string {
    return this.info.id;
  }

  get title(): string {
    return this.info.title;
  }

  get unit(): string {
    return this.info.unit;
  }

  get target(): string {
    return this.info.target;
  }

  /** Declared pair distances within the ones the API knows; both when none are. */
  get hops(): number[] {
    const declared = (this.info.hops ?? KNOWN_HOPS).filter((hop) => KNOWN_HOPS.includes(hop));
    return declared.length > 0 ? declared : [...KNOWN_HOPS];
  }
}

export interface PanelOptions {
  title?: string;
  /** Position and size; defaults to the left edge below every existing panel. */
  layout?: PanelLayoutModel;
  /** Dashboard-unique ID; defaults to a readable ID derived from the content. */
  panelId?: string;
}

export interface MetricPanelOptions extends PanelOptions {
  /** Days back from evaluation time, or a period object; the last 14 days by default. */
  period?: PeriodInput;
  /** Overrides of the metric's parameter defaults. */
  params?: Record<string, ParamValue>;
  view?: "map" | "table";
  direction?: "both" | "forward" | "reverse";
  /** Pair distances shown; defaults to the ones the metric declares. */
  hops?: number[];
}

export interface DashboardOptions {
  name: string;
  /** Settings left undefined are not sent: server defaults on create, stored values on update. */
  description?: string;
  visibility?: Visibility;
  chipId?: string;
  panels?: DashboardPanelModel[];
}

function period(input: PeriodInput | undefined): RelativePeriod | AbsolutePeriod {
  if (input === undefined) return { kind: "relative", days: 14 };
  if (typeof input === "number") return { kind: "relative", days: input };
  if (input && typeof input === "object") return input;
  throw new TypeError("period must be a number of days or a period object");
}

/**
 * A custom dashboard to save: name, settings and panels on a 12-column grid.
 * `addMetric` and `addMarkdown` place a new panel at the left edge below every
 * existing panel, sized as the dashboard editor sizes new panels, with a
 * readable ID unique within the dashboard. `panels` may be edited directly.
 */
export class Dashboard {
  name: string;
  description?: string;
  visibility?: Visibility;
  chipId?: string;
  panels: DashboardPanelModel[];

  constructor(options: DashboardOptions) {
    this.name = options.name;
    if (options.description !== undefined) this.description = options.description;
    if (options.visibility !== undefined) this.visibility = options.visibility;
    if (options.chipId !== undefined) this.chipId = options.chipId;
    this.panels = [...(options.panels ?? [])];
  }

  /** A definition holding a saved dashboard's settings and panels, ready to edit. */
  static fromResponse(response: CustomDashboardResponse): Dashboard {
    return new Dashboard({
      name: response.name,
      description: response.description,
      visibility: response.visibility,
      ...(response.chip_id !== null ? { chipId: response.chip_id } : {}),
      panels: response.panels.map(({ panel_id, type, title, layout, config }) => ({
        panel_id,
        type,
        ...(title !== undefined ? { title } : {}),
        layout: { ...layout },
        ...(config !== undefined ? { config: structuredClone(config) } : {}),
      })),
    });
  }

  private nextLayout(type: string): PanelLayoutModel {
    const bottom = this.panels.reduce((max, panel) => Math.max(max, panel.layout.y + panel.layout.h), 0);
    return { x: 0, y: bottom, ...(PANEL_SIZES[type] ?? { w: 6, h: 3 }) };
  }

  private panelId(base: string): string {
    const slug = base.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "panel";
    const taken = new Set(this.panels.map((panel) => panel.panel_id));
    let candidate = slug.slice(0, MAX_PANEL_ID);
    for (let number = 2; taken.has(candidate); number += 1) {
      const suffix = `-${number}`;
      candidate = `${slug.slice(0, MAX_PANEL_ID - suffix.length)}${suffix}`;
    }
    return candidate;
  }

  private add(panel: DashboardPanelModel): DashboardPanelModel {
    if (this.panels.some((existing) => existing.panel_id === panel.panel_id)) {
      throw new Error(`panel_id ${JSON.stringify(panel.panel_id)} is already on the dashboard`);
    }
    this.panels.push(panel);
    return panel;
  }

  /**
   * Add a `metric_script` panel pinned to `metric`'s script revision. The
   * server checks the script, revision, metric, parameters and hops on save.
   */
  addMetric(metric: ScriptMetric, options: MetricPanelOptions = {}): DashboardPanelModel {
    if (!(metric instanceof ScriptMetric)) {
      throw new TypeError("metric must be a ScriptMetric from SavedScript.metric(...)");
    }
    const config: MetricScriptPanelConfig = {
      script_id: metric.scriptId,
      script_revision: metric.revision,
      metric_id: metric.id,
      period: period(options.period),
      params: { ...(options.params ?? {}) },
      view: options.view ?? "map",
      direction: options.direction ?? "both",
      hops: options.hops ? [...options.hops] : metric.hops,
    };
    return this.add({
      panel_id: options.panelId ?? this.panelId(metric.id),
      type: "metric_script",
      title: options.title ?? metric.title,
      layout: options.layout ?? this.nextLayout("metric_script"),
      config: { ...config },
    });
  }

  /** Add a `markdown` note panel. */
  addMarkdown(content: string, options: PanelOptions = {}): DashboardPanelModel {
    return this.add({
      panel_id: options.panelId ?? this.panelId("markdown"),
      type: "markdown",
      title: options.title ?? "",
      layout: options.layout ?? this.nextLayout("markdown"),
      config: { content },
    });
  }

  private fields(): CustomDashboardCreateRequest {
    return {
      name: this.name,
      panels: this.panels.map((panel) => ({ ...panel })),
      ...(this.description !== undefined ? { description: this.description } : {}),
      ...(this.visibility !== undefined ? { visibility: this.visibility } : {}),
      ...(this.chipId !== undefined ? { chip_id: this.chipId } : {}),
    };
  }

  /** The `POST /custom-dashboards` body. */
  createRequest(): CustomDashboardCreateRequest {
    return this.fields();
  }

  /** The `PATCH /custom-dashboards/{id}` body; its panels replace the stored ones. */
  updateRequest(expectedVersion?: number): CustomDashboardUpdateRequest {
    return { ...this.fields(), ...(expectedVersion !== undefined ? { expected_version: expectedVersion } : {}) };
  }
}

function diagnosticText(response: MetricScriptResponse): string[] {
  return response.diagnostics.map(
    (diagnostic) => `${typeof diagnostic.line === "number" ? `line ${diagnostic.line}: ` : ""}${diagnostic.message}`,
  );
}

/**
 * A metric script as the server stored it, bound to one revision: the one a
 * create or update produced (or kept, when the source was unchanged), valid or
 * not; after `scripts.get` the active (last valid) revision unless another is
 * asked for. `metric` refuses an invalid revision instead of falling back.
 */
export class SavedScript {
  constructor(
    /** The script as the API returned it. */
    readonly response: MetricScriptResponse,
    readonly revision: number | null,
  ) {}

  get scriptId(): string {
    return this.response.script_id;
  }

  get name(): string {
    return this.response.name;
  }

  private entry(): MetricScriptRevision | undefined {
    return this.response.revisions.find((entry) => entry.revision === this.revision);
  }

  /** Whether the bound revision validated, so its metrics can back panels. */
  get valid(): boolean {
    return this.entry()?.status === "valid";
  }

  /** Problems the server reported for the latest saved source. */
  get diagnostics(): string[] {
    return this.revision === this.response.revision ? diagnosticText(this.response) : [];
  }

  /** The catalog of the bound revision; empty when it is invalid. */
  get metrics(): MetricInfo[] {
    return [...(this.entry()?.metrics ?? [])];
  }

  /** The metric `metricId` of the bound revision; `MetricScriptError` when it cannot back a panel. */
  metric(metricId: string): ScriptMetric {
    const where = `metric script '${this.name}' (${this.scriptId})`;
    if (this.revision === null) throw new MetricScriptError(`${where} has no valid revision`, this.scriptId, null);
    if (!this.entry()) {
      throw new MetricScriptError(`revision ${this.revision} of ${where} is not in its history`, this.scriptId, this.revision);
    }
    if (!this.valid) {
      const diagnostics = this.diagnostics;
      throw new MetricScriptError(
        [`revision ${this.revision} of ${where} did not validate`, ...diagnostics.map((line) => `- ${line}`)].join("\n"),
        this.scriptId,
        this.revision,
        diagnostics,
      );
    }
    const catalog = this.metrics;
    const info = catalog.find((entry) => entry.id === metricId);
    if (!info) {
      const known = catalog.map((entry) => entry.id).join(", ") || "none";
      throw new MetricScriptError(
        `revision ${this.revision} of ${where} has no metric '${metricId}'; it declares: ${known}`,
        this.scriptId,
        this.revision,
      );
    }
    return new ScriptMetric(this.scriptId, this.revision, info);
  }
}

/** The project's metric scripts, reached as `qdash.scripts`. */
export class Scripts {
  constructor(private readonly client: QDashClient) {}

  /** Scripts visible to the caller: shared with the project or their own. */
  async list(): Promise<MetricScriptSummary[]> {
    return (await this.client.listMetricScripts()).scripts;
  }

  /** A saved script bound to `revision`, by default its active (last valid) revision. */
  async get(scriptId: string, options: { revision?: number } = {}): Promise<SavedScript> {
    const response = await this.client.getMetricScript(scriptId);
    return new SavedScript(response, options.revision ?? response.active_revision);
  }

  /** A local `Script` holding a starter template's source; nothing is saved. */
  async template(templateId: string, options: Partial<Omit<ScriptOptions, "source">> = {}): Promise<Script> {
    const { templates } = await this.client.listMetricScriptTemplates();
    const template = templates.find((entry) => entry.template_id === templateId);
    if (!template) {
      const known = templates.map((entry) => entry.template_id).join(", ");
      throw new Error(`unknown metric script template '${templateId}'; known: ${known}`);
    }
    return new Script({
      ...options,
      name: options.name ?? template.name,
      description: options.description ?? template.description,
      source: template.source,
    });
  }

  /** Compile source on the server and return its catalog or diagnostics; saves nothing. */
  validate(script: Script | string): Promise<MetricScriptValidateResponse> {
    return this.client.validateMetricScript(typeof script === "string" ? script : script.source);
  }

  /** Save a new script; the result is bound to its first revision, valid or not. */
  async create(script: Script): Promise<SavedScript> {
    const response = await this.client.createMetricScript(script.createRequest());
    return new SavedScript(response, response.revision);
  }

  /**
   * Save `script` over the script `target` names. New source becomes the next
   * revision; source equal to the latest adds none. The result is bound to the
   * latest revision. A `SavedScript` target refuses (409) a script saved again
   * since it was read; `expectedRevision` sets that guard for an ID.
   */
  async update(
    target: string | SavedScript,
    script: Script,
    options: { expectedRevision?: number } = {},
  ): Promise<SavedScript> {
    const scriptId = typeof target === "string" ? target : target.scriptId;
    const expected = options.expectedRevision ?? (typeof target === "string" ? undefined : target.response.revision);
    const response = await this.client.updateMetricScript(scriptId, script.updateRequest(expected));
    return new SavedScript(response, response.revision);
  }
}

/** A custom dashboard as the server stored it. */
export class SavedDashboard {
  constructor(
    /** The dashboard as the API returned it. */
    readonly response: CustomDashboardResponse,
  ) {}

  get dashboardId(): string {
    return this.response.dashboard_id;
  }

  get name(): string {
    return this.response.name;
  }

  /** The write counter `dashboards.update` sends so a newer save is not overwritten. */
  get version(): number {
    return this.response.version;
  }

  /** A local copy of this dashboard's settings and panels to change and save back. */
  edit(): Dashboard {
    return Dashboard.fromResponse(this.response);
  }
}

/** The project's custom dashboards, reached as `qdash.dashboards`. */
export class Dashboards {
  constructor(private readonly client: QDashClient) {}

  /** Dashboards visible to the caller: shared with the project or their own. */
  async list(): Promise<CustomDashboardResponse[]> {
    return (await this.client.listCustomDashboards()).dashboards;
  }

  async get(dashboardId: string): Promise<SavedDashboard> {
    return new SavedDashboard(await this.client.getCustomDashboard(dashboardId));
  }

  /** Save a new dashboard owned by the caller. */
  async create(dashboard: Dashboard): Promise<SavedDashboard> {
    return new SavedDashboard(await this.client.createCustomDashboard(dashboard.createRequest()));
  }

  /**
   * Replace the settings and panels of the dashboard `target` names. Refused
   * (409) when it changed since the version the save is based on:
   * `expectedVersion`, else a `SavedDashboard` target's version, else the
   * version read just before saving. Nothing is retried.
   */
  async update(
    target: string | SavedDashboard,
    dashboard: Dashboard,
    options: { expectedVersion?: number } = {},
  ): Promise<SavedDashboard> {
    const dashboardId = typeof target === "string" ? target : target.dashboardId;
    const expected =
      options.expectedVersion ??
      (typeof target === "string" ? (await this.client.getCustomDashboard(dashboardId)).version : target.version);
    return new SavedDashboard(await this.client.updateCustomDashboard(dashboardId, dashboard.updateRequest(expected)));
  }
}
