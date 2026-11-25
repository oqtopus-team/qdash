import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { type FlowDocument, useFlowDocument } from "@/components/features/flow/useFlowDocument";

/** The left pane shows the page's workflow (the URL); the right pane, in split view, another. */
export type Pane = "primary" | "secondary";

export const PANE_LABEL: Record<Pane, string> = {
  primary: "Left",
  secondary: "Right",
};

interface UseWorkflowEditorPanesOptions {
  /** The page's workflow, shown in the left pane. */
  routeName: string;
  /** `?split=<name>`: the right pane's workflow, carried over when the left pane opens another. */
  initialSplit: string | null;
  /** Runs an action once any unsaved draft among the given workflows may be dropped. */
  confirmDiscard: (candidates: FlowDocument[], action: () => void) => void;
  /** Called when the split opens, so the user can pick the right pane's workflow. */
  onSplitOpened: () => void;
}

/**
 * The editor's panes: each edits and saves its own workflow, and the active one is what header
 * actions, Properties, the status bar and the Explorer act on. Replacing, closing or leaving a
 * pane's workflow asks first when it has an unsaved draft.
 */
export function useWorkflowEditorPanes({
  routeName,
  initialSplit,
  confirmDiscard,
  onSplitOpened,
}: UseWorkflowEditorPanesOptions) {
  const router = useRouter();
  const [isSplitView, setIsSplitView] = useState(Boolean(initialSplit));
  const [splitName, setSplitName] = useState<string | null>(
    initialSplit && initialSplit !== routeName ? initialSplit : null,
  );
  const [activePane, setActivePane] = useState<Pane>("primary");

  const primary = useFlowDocument(routeName);
  const secondary = useFlowDocument(isSplitView ? splitName : null);
  const docs: Record<Pane, FlowDocument> = { primary, secondary };
  const currentPane: Pane = isSplitView && activePane === "secondary" ? "secondary" : "primary";

  // Warn before leaving with unsaved changes in either pane
  const hasUnsavedChanges = primary.isDirty || secondary.isDirty;
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [hasUnsavedChanges]);

  /** Navigate away from the editor, first confirming either pane's draft. */
  const leaveTo = (href: string) => confirmDiscard([primary, secondary], () => router.push(href));

  // Open a workflow from the Explorer in the active pane.
  const openFlow = (flowName: string) => {
    const target = currentPane;
    const other: Pane = target === "primary" ? "secondary" : "primary";
    // A workflow already open in the other pane is focused there, never opened twice.
    if (isSplitView && docs[other].name === flowName) {
      setActivePane(other);
      return;
    }
    if (docs[target].name === flowName) return;
    if (target === "secondary") {
      confirmDiscard([secondary], () => setSplitName(flowName));
      return;
    }
    // The left pane is the page's workflow: opening another navigates, keeping the right pane's
    // workflow open; the page reloads both, so either pane's draft is confirmed first.
    confirmDiscard(isSplitView ? [primary, secondary] : [primary], () => {
      const split = isSplitView && splitName ? `?split=${encodeURIComponent(splitName)}` : "";
      router.push(`/workflow/${encodeURIComponent(flowName)}${split}`);
    });
  };

  const toggleSplit = () => {
    if (!isSplitView) {
      // The new right pane waits for a workflow picked in the Explorer.
      setIsSplitView(true);
      setActivePane("secondary");
      onSplitOpened();
      return;
    }
    confirmDiscard([secondary], () => {
      setIsSplitView(false);
      setSplitName(null);
      setActivePane("primary");
    });
  };

  /** Empties the right pane when its workflow was deleted; the left pane stays open. */
  const forgetSplitFlow = (flowName: string) =>
    setSplitName((current) => (current === flowName ? null : current));

  return {
    primary,
    secondary,
    docs,
    isSplitView,
    currentPane,
    setActivePane,
    openFlow,
    toggleSplit,
    leaveTo,
    forgetSplitFlow,
  };
}
