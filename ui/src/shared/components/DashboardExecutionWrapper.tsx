import { IoTime } from "react-icons/io5";
import { EmbeddedAnalysisView } from "./EmbeddedAnalysisView";
import { ExecutionPageContent } from "@/app/execution/components/ExecutionPageContent";

/**
 * Dashboard wrapper for ExecutionPage - shows the full execution history
 */
export function DashboardExecutionView({
  height = "600px",
  focusOnContent = false,
}: {
  height?: string;
  focusOnContent?: boolean;
}) {
  return (
    <EmbeddedAnalysisView
      title="Execution History"
      icon={<IoTime />}
      navigateTo="/execution"
      height={height}
    >
      <div
        className={`${focusOnContent ? "dashboard-focus-execution" : ""} overflow-hidden`}
      >
        <ExecutionPageContent />
      </div>
    </EmbeddedAnalysisView>
  );
}
