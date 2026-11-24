/**
 * Names for the generated API types the SDK helpers take and return. Every type of the API is
 * also reachable as `QDashApi.<Name>`; these aliases keep the names the SDK has always exported.
 * Objects use the API's own snake_case keys and are sent as written.
 */
import type { QDashApi } from "./_generated/index.js";

export type AbsolutePeriod = QDashApi.AbsolutePeriod;
export type CalibrationPipelineSpec = QDashApi.CalibrationPipelineSpec;
export type CalibrationPipelineSpecStepsItem = QDashApi.CalibrationPipelineSpecStepsItem;
export type ChipMetricsResponse = QDashApi.ChipMetricsResponse;
export type CooldownResponse = QDashApi.CooldownResponse;
export type CouplingResponse = QDashApi.CouplingResponse;
export type DashboardPanelModel = QDashApi.DashboardPanelModel;
export type DashboardResponse = QDashApi.DashboardResponse;
export type ExecuteFlowResponse = QDashApi.ExecuteFlowResponse;
export type ExecutePipelineResponse = QDashApi.ExecutePipelineResponse;
export type ExecutionResponseDetail = QDashApi.ExecutionResponseDetail;
export type FlowSummary = QDashApi.FlowSummary;
export type GetFlowResponse = QDashApi.GetFlowResponse;
export type MetricInfo = QDashApi.MetricInfo;
export type MetricScriptPanelConfig = QDashApi.MetricScriptPanelConfig;
export type MetricScriptPanelConfigPeriod = QDashApi.MetricScriptPanelConfigPeriod;
export type MetricScriptResponse = QDashApi.MetricScriptResponse;
export type MetricScriptRevision = QDashApi.MetricScriptRevision;
export type MetricScriptSummary = QDashApi.MetricScriptSummary;
export type MetricScriptValidateResponse = QDashApi.MetricScriptValidateResponse;
export type MetricValue = QDashApi.MetricValue;
export type PanelLayoutModel = QDashApi.PanelLayoutModel;
export type ParameterModel = QDashApi.ParameterModel;
export type PipelineCatalogResponse = QDashApi.PipelineCatalogResponse;
export type PipelineProblem = QDashApi.PipelineProblem;
export type PipelineTargets = QDashApi.PipelineTargets;
export type QubitResponse = QDashApi.QubitResponse;
export type RelativePeriod = QDashApi.RelativePeriod;
export type ReportedLaunchOrigin = QDashApi.ReportedLaunchOrigin;
export type Task = QDashApi.Task;
export type TaskCall = QDashApi.TaskCall;
export type TaskHistoryResponse = QDashApi.TaskHistoryResponse;
export type TaskResultListItem = QDashApi.TaskResultListItem;
export type TaskResultListResponse = QDashApi.TaskResultListResponse;
export type TaskResultResponse = QDashApi.TaskResultResponse;
export type TimeSeriesData = QDashApi.TimeSeriesData;
export type ValidatePipelineResponse = QDashApi.ValidatePipelineResponse;

/** A `CustomOneQubit` step as a pipeline spec holds it, with its `type`. */
export type CustomOneQubitStep = QDashApi.CalibrationPipelineSpecStepsItem.CustomOneQubit;

// Request bodies the SDK builds locally; the route's path parameters are added when it is sent.
export type MetricScriptCreateRequest = QDashApi.MetricScriptCreateRequest;
export type MetricScriptUpdateRequest = Omit<QDashApi.MetricScriptUpdateRequest, "script_id">;
export type DashboardCreateRequest = QDashApi.DashboardCreateRequest;
export type DashboardUpdateRequest = Omit<QDashApi.DashboardUpdateRequest, "dashboard_id">;
