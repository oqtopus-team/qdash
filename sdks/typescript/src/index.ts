/**
 * `@oqtopus-team/qdash-sdk`: the QDash API from TypeScript, with calibration, workflow and
 * dashboard helpers, modelled on the Python `qdash.sdk`.
 *
 * The SDK is self-contained: it does not depend on `@oqtopus-team/qdash-client`. A `QDash`
 * session holds the configuration, authentication and project: `new QDash(config)`,
 * `QDash.fromEnv()` or `await QDash.fromProfile()` (the TOML config file shared with the
 * Python SDK). `qdash.api` is the client of the whole API, generated from its OpenAPI document
 * with Fern; its types are in the `QDashApi` namespace. On top of it, `qdash.chip(chipId)`
 * validates (`validateCalibration`) or dispatches (`calibrate`) a calibration;
 * `qdash.workflows` lists, reads and runs the project's registered workflows;
 * `qdash.pipelines` works with whole specs; `qdash.scripts` and `qdash.dashboards` save
 * metric scripts and custom dashboards defined with `Script` and `Dashboard`;
 * `qdash.taskResults` combines task-result reads, such as `compareLatest` and `evidence`;
 * `qdash.run(executionId)` follows any dispatched run.
 */
export { QDash } from "./session.js";
export type { QDashFactoryOptions, QDashSessionOptions } from "./session.js";
export {
  DEFAULT_PROFILE,
  INI_CONFIG_DEPRECATION_CODE,
  QDashConfig,
  defaultConfigPath,
  legacyConfigPath,
} from "./config.js";
export type { QDashConfigOptions } from "./config.js";
export { QDashApiClient, QDashApi } from "./_generated/index.js";
export type { BaseClientOptions, BaseRequestOptions } from "./_generated/index.js";
export {
  ApiError,
  ApiTimeoutError,
  QDashApiError,
  QDashAuthError,
  QDashConfigError,
  QDashConflictError,
  QDashNotFoundError,
  QDashResultUnknownError,
  QDashTimeoutError,
  QDashTransportError,
  QDashValidationError,
} from "./errors.js";
export type { QDashErrorOptions } from "./errors.js";
export { CalibrationRun, Chip, PipelineRun, Pipelines } from "./pipelines.js";
export type { PipelineLaunchOptions, PipelineRecording, PipelineSpecInput, PipelineTarget } from "./pipelines.js";
export { Workflow, WorkflowRun, Workflows } from "./workflows.js";
export type { WorkflowRunOptions } from "./workflows.js";
export {
  Dashboard,
  Dashboards,
  MetricScriptError,
  SavedDashboard,
  SavedScript,
  Script,
  ScriptMetric,
  Scripts,
} from "./dashboards.js";
export type {
  DashboardOptions,
  MetricPanelOptions,
  PanelOptions,
  ParamValue,
  PeriodInput,
  ScriptOptions,
  Visibility,
} from "./dashboards.js";
export { COMPARE_LATEST_DEFAULT_ROWS, COMPARE_LATEST_MAX_ROWS, TaskResults } from "./results.js";
export type {
  CompareLatestOptions,
  ComparedTaskResults,
  OutputParameterChange,
  TaskResultComparison,
} from "./results.js";
export { COOLDOWN_NOT_ASSOCIATED } from "./evidence.js";
export type {
  CooldownContext,
  ExecutionContext,
  StoredOutput,
  TargetContext,
  TaskResultContext,
  TaskResultEvidence,
  TaskResultEvidenceOptions,
} from "./evidence.js";
export { Run, runStatus } from "./runs.js";
export type { RunResult, WaitOptions } from "./runs.js";
export { calibrationSpec, customOneQubit, muxTargets, qubitTargets, sweep } from "./definitions.js";
export type { CalibrationOptions, SweepDeclaration } from "./definitions.js";
export type {
  CalibrationPipelineSpec,
  CalibrationPipelineSpecStepsItem,
  ChipMetricsResponse,
  CooldownResponse,
  CouplingResponse,
  CustomOneQubitStep,
  DashboardPanelModel,
  DashboardResponse,
  ExecuteFlowResponse,
  ExecutePipelineResponse,
  ExecutionResponseDetail,
  FlowSummary,
  GetFlowResponse,
  MetricInfo,
  MetricScriptPanelConfig,
  MetricScriptResponse,
  MetricScriptSummary,
  MetricScriptValidateResponse,
  MetricValue,
  ParameterModel,
  PipelineCatalogResponse,
  PipelineProblem,
  PipelineTargets,
  QubitResponse,
  Task,
  TaskCall,
  TaskHistoryResponse,
  TaskResultListItem,
  TaskResultListResponse,
  TaskResultResponse,
  TimeSeriesData,
  ValidatePipelineResponse,
} from "./types.js";
