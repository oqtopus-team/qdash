"use client";

import type { OnMount } from "@monaco-editor/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  ArrowLeft,
  CircleAlert,
  CircleCheck,
  Copy,
  Play,
  Save,
  ShieldCheck,
  TextAlignStart,
  TriangleAlert,
} from "lucide-react";
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from "react-resizable-panels";

import {
  formatMetricScriptSource,
  getListMetricScriptsQueryKey,
  useCopyMetricScript,
  useEvaluateMetricScript,
  useEvaluateMetricScriptDraft,
  useValidateMetricScript,
} from "@/client/metric-script/metric-script";
import type { MetricInfo, MetricScriptResponseVisibility, ScriptDiagnostic } from "@/schemas";
import { VisibilityLabel } from "@/components/features/dashboards/VisibilityLabel";
import { ErrorCard } from "@/components/ui/ErrorCard";
import { PageContainer } from "@/components/ui/PageContainer";
import { useToast } from "@/components/ui/Toast";
import { useChatDock } from "@/contexts/ChatDockContext";
import { useProject } from "@/contexts/ProjectContext";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { monoFontFamily, remeasureMonacoFontsWhenLoaded } from "@/lib/fonts";
import {
  attachPythonFormatter,
  describeFormatProblem,
  formatEditorDocument,
  type FormatRun,
  type FormatterEditor,
} from "@/lib/pythonFormatter";
import type { MetricScriptEditorContext } from "@/types/copilotChat";
import { getApiErrorMessage } from "@/lib/utils/apiError";

import { describeMetricError } from "./errors";
import { declaredHops } from "./hops";
import { paramsFromInputs } from "./parameters";
import { defaultPeriod, periodError } from "./periods";
import { PreviewControls, type PreviewSettings } from "./PreviewControls";
import { DiagnosticLocation, MetricResultView } from "./render/MetricResultView";
import { useChipTopologyId, useDefaultChipId } from "./useChipTopology";
import { useMetricScriptDocument } from "./useMetricScriptDocument";

// Monaco Editor is only available on the client side.
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const EDITOR_OPTIONS = {
  minimap: { enabled: false },
  fontSize: 14,
  fontFamily: monoFontFamily,
  fontLigatures: true,
  lineNumbers: "on" as const,
  automaticLayout: true,
  scrollBeyondLastLine: true,
  padding: { top: 12, bottom: 12 },
  wordWrap: "on" as const,
  tabSize: 4,
  insertSpaces: true,
  renderLineHighlight: "all" as const,
  bracketPairColorization: { enabled: true },
  guides: { bracketPairs: true, indentation: true },
  stickyScroll: { enabled: true },
  scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
};

const MARKER_OWNER = "metric-script";

/** Below Tailwind's `md` breakpoint the editor and the side pane become tabs. */
const NARROW_QUERY = "(max-width: 767px)";

/** Heading id of the Settings section; other pages link to it with a URL fragment. */
const SETTINGS_ANCHOR = "metric-script-settings";

type EditorPane = "code" | "details";

const EDITOR_PANES: Array<{ value: EditorPane; label: string }> = [
  { value: "code", label: "Code" },
  { value: "details", label: "Settings & preview" },
];

/** The last check of the script's text: a validation, a save, or what the server stored. */
interface ScriptReport {
  kind: "loaded" | "validated" | "saved";
  ok: boolean;
  diagnostics: ScriptDiagnostic[];
  /** Catalog found by a validation; saved reports use the script's active catalog. */
  metrics: MetricInfo[] | null;
  /** The text the report is about. */
  code: string;
}

interface MonacoEditorLike {
  revealLineInCenter: (line: number) => void;
  setPosition: (position: { lineNumber: number; column: number }) => void;
  focus: () => void;
  getModel: () => unknown;
}

interface DisposableModel {
  dispose?: () => void;
}

interface MonacoLike {
  editor?: {
    setModelMarkers?: (model: unknown, owner: string, markers: unknown[]) => void;
  };
  MarkerSeverity?: { Error: number };
}

function Section({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const headingId = `metric-script-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-2 border-b border-base-300 p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 id={headingId} className="text-sm font-medium">
          {title}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

/** Python editor for one metric script with settings, validation, preview and diagnostics. */
export function MetricScriptEditorPageContent({ scriptId }: { scriptId: string }) {
  const id = useId();
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { canEdit } = useProject();
  const doc = useMetricScriptDocument(scriptId);
  const { script, isReady, code, setCode, settings, setSettings, isDirty } = doc;
  const mayEdit = canEdit && Boolean(script?.can_edit);
  const readOnly = !mayEdit;

  const validateMutation = useValidateMetricScript();
  const draftMutation = useEvaluateMetricScriptDraft();
  const savedMutation = useEvaluateMetricScript();
  const copyMutation = useCopyMetricScript();
  const previewMutation = canEdit ? draftMutation : savedMutation;

  const [report, setReport] = useState<ScriptReport | null>(null);
  const reportSource = report ?? (script ? loadedReport(script) : null);

  const defaultChipId = useDefaultChipId();
  const [preview, setPreview] = useState<PreviewSettings>(() => ({
    chipId: "",
    metricId: "",
    period: defaultPeriod(),
    paramInputs: {},
    view: "map",
    direction: "both",
    hops: [1, 2],
  }));
  const chipId = preview.chipId || defaultChipId;
  const topologyId = useChipTopologyId(chipId);

  // Metrics of the latest validation of this text, else the active (last-good) catalog.
  const metrics = useMemo<MetricInfo[]>(() => {
    if (report?.kind === "validated" && report.ok && report.metrics && report.code === code) {
      return report.metrics;
    }
    return script?.metrics ?? [];
  }, [code, report, script?.metrics]);
  const metric = metrics.find((entry) => entry.id === preview.metricId) ?? metrics[0];
  const metricId = metric?.id ?? "";
  const effectiveHops = metric?.target === "pair" ? preview.hops : undefined;

  const updatePreview = useCallback(
    (patch: Partial<PreviewSettings>) => setPreview((current) => ({ ...current, ...patch })),
    [],
  );

  // Editor handles for jumping to diagnostics and marking them in the text.
  const editorRef = useRef<MonacoEditorLike | null>(null);
  const monacoRef = useRef<MonacoLike | null>(null);
  const [editorMounts, setEditorMounts] = useState(0);
  // Format Document run from the context menu or Shift+Alt+F reports here.
  const reportFormatRun = useCallback(
    (run: FormatRun, explicit: boolean) => {
      const problem = describeFormatProblem(run);
      if (problem) {
        toast.error("Could not format the script", { description: problem });
      } else if (explicit && run.status === "unchanged") {
        toast.info("The script is already formatted");
      }
    },
    [toast],
  );
  const reportFormatRunRef = useRef(reportFormatRun);
  useEffect(() => {
    reportFormatRunRef.current = reportFormatRun;
  });
  const handleMount = useCallback<OnMount>((editor, monaco) => {
    editorRef.current = editor as unknown as MonacoEditorLike;
    monacoRef.current = monaco as unknown as MonacoLike;
    remeasureMonacoFontsWhenLoaded(monaco);
    // Format Document formats with the project's Ruff settings; detached when the editor goes.
    attachPythonFormatter(monaco, editor, {
      format: async (source) => (await formatMetricScriptSource({ source })).data,
      onRun: (run) => reportFormatRunRef.current(run, false),
    });
    setEditorMounts((count) => count + 1);
  }, []);

  // On narrow screens only one pane shows at a time; both stay mounted so switching keeps the
  // editor, its undo history, and the preview result.
  const isNarrow = useMediaQuery(NARROW_QUERY);
  const [pane, setPane] = useState<EditorPane>("code");

  const jumpToLine = useCallback(
    (line: number, column?: number | null) => {
      const reveal = () => {
        const editor = editorRef.current;
        if (!editor) return;
        editor.revealLineInCenter(line);
        editor.setPosition({ lineNumber: line, column: column ?? 1 });
        editor.focus();
      };
      if (isNarrow && pane !== "code") {
        // Let the editor lay out at its visible size before it scrolls to the line.
        setPane("code");
        requestAnimationFrame(reveal);
        return;
      }
      reveal();
    },
    [isNarrow, pane],
  );

  // The editor keeps its model across remounts (crossing the narrow breakpoint swaps the
  // layout); drop the model once the page itself goes away.
  useEffect(
    () => () => {
      (editorRef.current?.getModel() as DisposableModel | null | undefined)?.dispose?.();
    },
    [],
  );

  // A link to #metric-script-settings shows the Settings section, on narrow screens by
  // switching to its pane first.
  const hasScript = Boolean(doc.script);
  useEffect(() => {
    if (!hasScript) return;
    const revealSettings = () => {
      if (window.location.hash !== `#${SETTINGS_ANCHOR}`) return;
      setPane("details");
      requestAnimationFrame(() =>
        document.getElementById(SETTINGS_ANCHOR)?.scrollIntoView({ block: "start" }),
      );
    };
    revealSettings();
    window.addEventListener("hashchange", revealSettings);
    return () => window.removeEventListener("hashchange", revealSettings);
  }, [hasScript]);

  const diagnostics = useMemo(() => reportSource?.diagnostics ?? [], [reportSource]);
  useEffect(() => {
    const monaco = monacoRef.current;
    const model = editorRef.current?.getModel();
    if (!monaco?.editor?.setModelMarkers || !model) return;
    monaco.editor.setModelMarkers(
      model,
      MARKER_OWNER,
      reportSource?.code === code
        ? diagnostics
            .filter((diagnostic) => diagnostic.line)
            .map((diagnostic) => ({
              severity: monaco.MarkerSeverity?.Error ?? 8,
              message: diagnostic.message,
              startLineNumber: diagnostic.line ?? 1,
              startColumn: diagnostic.column ?? 1,
              endLineNumber: diagnostic.line ?? 1,
              endColumn: (diagnostic.column ?? 1) + 1000,
            }))
        : [],
    );
  }, [code, diagnostics, reportSource?.code, editorMounts]);

  const handleValidate = () => {
    const source = code;
    validateMutation.mutate(
      { data: { source } },
      {
        onSuccess: (response) => {
          setReport({
            kind: "validated",
            ok: response.data.ok,
            diagnostics: response.data.diagnostics,
            metrics: response.data.metrics,
            code: source,
          });
          if (response.data.ok) {
            toast.success(
              `No problems found; ${response.data.metrics.length} ${response.data.metrics.length === 1 ? "metric" : "metrics"}`,
            );
          }
        },
        onError: (error) =>
          toast.error(describeMetricError(error, "Failed to validate the script").message),
      },
    );
  };

  const { params, errors: paramErrors } = paramsFromInputs(metric, preview.paramInputs);
  const previewBlocked: string | null = !chipId
    ? "Select a chip"
    : !metric
      ? "No metric to preview"
      : (periodError(preview.period) ??
        (Object.keys(paramErrors).length > 0 ? "Fix the highlighted parameters" : null));

  const handlePreview = () => {
    if (previewBlocked || !metric) return;
    const base = { metric_id: metric.id, chip_id: chipId, period: preview.period, params };
    setPane("details");
    if (canEdit) {
      draftMutation.mutate({ data: { ...base, source: code } });
    } else {
      savedMutation.mutate({ scriptId, data: base });
    }
  };

  // Format the draft in the editor without saving it; undo restores the previous text.
  const [isFormatting, setIsFormatting] = useState(false);
  const canFormat = mayEdit && isReady && !isFormatting && !doc.isSaving;
  const handleFormat = async () => {
    if (!canFormat) return;
    setIsFormatting(true);
    try {
      reportFormatRun(
        await formatEditorDocument(editorRef.current as FormatterEditor | null, code),
        true,
      );
    } finally {
      setIsFormatting(false);
    }
  };

  // Save formats the draft first, so the editor shows the source that is saved. A draft that
  // cannot be parsed is saved as written: it becomes a revision with errors and the last
  // valid revision stays active. A draft edited while the formatter ran is not saved.
  const formatForSave = async (draft: string): Promise<string | null> => {
    const run = await formatEditorDocument(editorRef.current as FormatterEditor | null, draft);
    if (run.status === "stale") {
      toast.warning("Not saved: the script changed while it was being formatted", {
        description: "Save again to save the current text.",
      });
      return null;
    }
    if (run.status === "failed") {
      toast.warning("Saving without formatting", { description: describeFormatProblem(run) });
    }
    return run.text;
  };

  const canSave =
    mayEdit && isReady && !doc.isSaving && !isFormatting && settings.name.trim() !== "";
  const save = async () => {
    if (!canSave) return;
    const saved = await doc.save(formatForSave);
    if (saved) {
      setReport({
        kind: "saved",
        ok: saved.status === "valid",
        diagnostics: saved.diagnostics,
        metrics: null,
        code: saved.source,
      });
    }
  };
  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  });

  // Cmd/Ctrl+S saves, wherever the focus is on the page.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveRef.current();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Warn before a reload or tab close drops the draft.
  useEffect(() => {
    if (!isDirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  // Tell the chat what is open here: the script and its current text, read when a turn is
  // sent; a proposed edit for this script replaces the draft.
  const { registerPage, refreshPage } = useChatDock();
  const pageState = useRef({
    scriptId,
    name: settings.name,
    ready: isReady,
    code,
    isDirty,
    setCode,
  });
  useEffect(() => {
    pageState.current = { scriptId, name: settings.name, ready: isReady, code, isDirty, setCode };
    refreshPage();
  });
  useEffect(
    () =>
      registerPage({
        current: () => {
          const { scriptId, name, ready, code, isDirty } = pageState.current;
          return {
            path: `/dashboards/scripts/${scriptId}`,
            title: `Metric script: ${name || scriptId}`,
            metricScript: ready
              ? ({ scriptId, name, code, dirty: isDirty } satisfies MetricScriptEditorContext)
              : undefined,
          };
        },
        applyCode: (next) => {
          if (!pageState.current.ready) return;
          pageState.current.setCode(next);
        },
      }),
    [registerPage],
  );

  const handleCopy = () => {
    copyMutation.mutate(
      { scriptId },
      {
        onSuccess: (response) => {
          void queryClient.invalidateQueries({ queryKey: getListMetricScriptsQueryKey() });
          toast.success(`Copied as "${response.data.name}"`);
          router.push(`/dashboards/scripts/${response.data.script_id}`);
        },
        onError: (error) => toast.error(getApiErrorMessage(error, "Failed to copy the script")),
      },
    );
  };

  if (doc.isLoading) {
    return (
      <div className="flex h-full flex-col gap-3 p-4" aria-busy="true" aria-label="Loading script">
        <div className="skeleton h-8 w-64" />
        <div className="skeleton min-h-0 flex-1" />
      </div>
    );
  }
  if (!script) {
    const notFound = isAxiosError(doc.error) && doc.error.response?.status === 404;
    return (
      <PageContainer maxWidth>
        <ErrorCard
          title={notFound ? "Metric script not found" : "Failed to load the metric script"}
          message={
            notFound
              ? "It was deleted, or its owner has not shared it with the project."
              : getApiErrorMessage(doc.error, "The script could not be loaded")
          }
        />
        <div className="mt-4 flex justify-center">
          <Link href="/dashboards?tab=scripts" className="btn btn-sm">
            <ArrowLeft data-icon="inline-start" aria-hidden="true" />
            All scripts
          </Link>
        </div>
      </PageContainer>
    );
  }

  const status = script.status;
  const active = script.active_revision;

  const editorPane = isReady ? (
    <Editor
      height="100%"
      language="python"
      theme="vs-dark"
      path={`metric-script/${scriptId}.py`}
      keepCurrentModel
      value={code}
      onChange={(value) => setCode(value ?? "")}
      onMount={handleMount}
      options={{ ...EDITOR_OPTIONS, readOnly, domReadOnly: readOnly }}
    />
  ) : (
    <div className="skeleton h-full w-full" />
  );

  const detailsPane = (
    <>
      <Section title="Settings">
        <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
          <fieldset className="fieldset min-w-0">
            <legend className="fieldset-legend">
              <label htmlFor={`${id}-name`}>Name</label>
            </legend>
            <input
              id={`${id}-name`}
              className={`input input-sm w-full ${settings.name.trim() ? "" : "input-error"}`}
              value={settings.name}
              maxLength={120}
              disabled={readOnly}
              onChange={(event) => setSettings({ name: event.target.value })}
            />
          </fieldset>
          <fieldset className="fieldset min-w-0">
            <legend className="fieldset-legend">
              <label htmlFor={`${id}-visibility`}>Visibility</label>
            </legend>
            <select
              id={`${id}-visibility`}
              className="select select-sm w-full"
              value={settings.visibility}
              disabled={readOnly}
              onChange={(event) =>
                setSettings({
                  visibility: event.target.value as MetricScriptResponseVisibility,
                })
              }
            >
              <option value="private">Private</option>
              <option value="project">Shared with project</option>
            </select>
          </fieldset>
        </div>
        <fieldset className="fieldset">
          <legend className="fieldset-legend">
            <label htmlFor={`${id}-description`}>Description</label>
          </legend>
          <textarea
            id={`${id}-description`}
            className="textarea textarea-sm w-full"
            rows={2}
            maxLength={2000}
            value={settings.description}
            disabled={readOnly}
            onChange={(event) => setSettings({ description: event.target.value })}
          />
        </fieldset>
      </Section>

      <Section
        title="Diagnostics"
        actions={
          reportSource && reportSource.code !== code ? (
            <span className="text-xs text-base-content/60">For an earlier version</span>
          ) : undefined
        }
      >
        {diagnostics.length > 0 ? (
          <ul className="flex flex-col gap-1.5 text-sm" data-testid="diagnostics">
            {diagnostics.map((diagnostic, index) => (
              <li key={`${diagnostic.line ?? "x"}-${index}`} className="flex gap-2 py-0.5">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-error" aria-hidden="true" />
                <DiagnosticLocation diagnostic={diagnostic} onJumpToLine={jumpToLine} />
              </li>
            ))}
          </ul>
        ) : reportSource?.ok ? (
          <p className="flex items-center gap-1.5 text-sm text-base-content/70">
            <CircleCheck className="h-4 w-4 text-success" aria-hidden="true" />
            {reportSource.kind === "validated" ? "Validation found no problems" : "No problems"}
          </p>
        ) : (
          <p className="text-sm text-base-content/60">Validate the script to check it</p>
        )}
      </Section>

      <Section title="Preview">
        <PreviewControls
          id={`${id}-preview`}
          metrics={metrics}
          value={{
            ...preview,
            chipId,
            metricId,
            hops: metric?.target === "pair" ? preview.hops : declaredHops(metric),
          }}
          onChange={updatePreview}
        />
        {!canEdit && (
          <p className="text-xs text-base-content/60">
            Viewers preview the active revision; only editors can run unsaved text.
          </p>
        )}
        <div className="h-[28rem] min-h-0">
          <MetricResultView
            result={previewMutation.data?.data}
            error={previewMutation.error}
            isLoading={previewMutation.isPending && !previewMutation.data}
            isFetching={previewMutation.isPending}
            topologyId={topologyId}
            view={preview.view}
            direction={preview.direction}
            hops={effectiveHops}
            onRetry={handlePreview}
            onJumpToLine={jumpToLine}
            emptyMessage="Choose a chip and metric, then press Preview"
          />
        </div>
      </Section>
    </>
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-base-100">
      <header className="flex flex-col gap-3 border-b border-base-300 bg-base-100 px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <Link
            href="/dashboards?tab=scripts"
            className="btn btn-ghost btn-sm btn-square shrink-0"
            aria-label="All scripts"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Link>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-medium">{settings.name || script.name}</h1>
            <div
              className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-base-content/60"
              data-testid="script-status"
            >
              <VisibilityLabel visibility={script.visibility} />
              <span>Saved r{script.revision}</span>
              {active ? (
                <span>Active r{active}</span>
              ) : (
                <span className="inline-flex items-center gap-1 text-warning">
                  <TriangleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  No valid revision
                </span>
              )}
              {isDirty && (
                <span className="inline-flex items-center gap-1 text-warning">
                  <CircleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  Unsaved changes
                </span>
              )}
              <span>by {script.owner_username}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canEdit && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={handleValidate}
              disabled={!isReady || validateMutation.isPending}
            >
              {validateMutation.isPending ? (
                <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
              ) : (
                <ShieldCheck data-icon="inline-start" aria-hidden="true" />
              )}
              Validate
            </button>
          )}
          <button
            type="button"
            className="btn btn-sm"
            onClick={handlePreview}
            disabled={!isReady || previewMutation.isPending || previewBlocked !== null}
            title={previewBlocked ?? undefined}
          >
            {previewMutation.isPending ? (
              <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
            ) : (
              <Play data-icon="inline-start" aria-hidden="true" />
            )}
            Preview
          </button>
          {canEdit && !script.can_edit && active !== null && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={handleCopy}
              disabled={copyMutation.isPending}
            >
              <Copy data-icon="inline-start" aria-hidden="true" />
              Copy to my scripts
            </button>
          )}
          {mayEdit && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void handleFormat()}
              disabled={!canFormat}
              title="Format with Ruff (Shift+Alt+F in the editor)"
            >
              {isFormatting ? (
                <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
              ) : (
                <TextAlignStart data-icon="inline-start" aria-hidden="true" />
              )}
              Format
            </button>
          )}
          {mayEdit && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void save()}
              disabled={!canSave}
              title="Save (Cmd/Ctrl+S)"
            >
              {doc.isSaving ? (
                <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
              ) : (
                <Save data-icon="inline-start" aria-hidden="true" />
              )}
              Save
            </button>
          )}
        </div>
      </header>

      {status === "invalid" && (
        <div
          role="status"
          className="alert alert-warning alert-soft rounded-none px-3 py-2 text-sm"
        >
          <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            {active
              ? `Revision r${script.revision} has errors. Dashboards keep using r${active}, the last revision that validated.`
              : "This script has no valid revision yet, so dashboards cannot use it."}
          </span>
        </div>
      )}

      {isNarrow ? (
        <>
          <div
            role="tablist"
            aria-label="Editor panes"
            className="tabs tabs-border shrink-0 border-b border-base-300"
          >
            {EDITOR_PANES.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                role="tab"
                id={`${id}-pane-tab-${value}`}
                aria-selected={pane === value}
                aria-controls={`${id}-pane-${value}`}
                className={`tab flex-1 ${pane === value ? "tab-active" : ""}`}
                onClick={() => setPane(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id={`${id}-pane-code`}
            aria-labelledby={`${id}-pane-tab-code`}
            hidden={pane !== "code"}
            className="min-h-0 flex-1 overflow-hidden"
          >
            {editorPane}
          </div>
          <div
            role="tabpanel"
            id={`${id}-pane-details`}
            aria-labelledby={`${id}-pane-tab-details`}
            hidden={pane !== "details"}
            className="min-h-0 flex-1 overflow-auto"
          >
            {detailsPane}
          </div>
        </>
      ) : (
        <PanelGroup orientation="horizontal" style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
          <Panel defaultSize="55%" minSize="25%" style={{ overflow: "hidden", minWidth: 0 }}>
            {editorPane}
          </Panel>
          <PanelResizeHandle className="w-1 cursor-col-resize bg-base-300 transition-colors hover:bg-primary/50" />
          <Panel defaultSize="45%" minSize="25%" style={{ overflow: "auto", minWidth: 0 }}>
            {detailsPane}
          </Panel>
        </PanelGroup>
      )}
    </div>
  );
}

function loadedReport(script: {
  status: string;
  diagnostics: ScriptDiagnostic[];
  source: string;
}): ScriptReport {
  return {
    kind: "loaded",
    ok: script.status === "valid",
    diagnostics: script.diagnostics,
    metrics: null,
    code: script.source,
  };
}
