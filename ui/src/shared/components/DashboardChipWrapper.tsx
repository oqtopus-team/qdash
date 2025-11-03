import { BsCpu } from "react-icons/bs";

import { EmbeddedAnalysisView } from "./EmbeddedAnalysisView";

import { ChipPageContent } from "@/app/chip/components/ChipPageContent";

/**
 * Dashboard wrapper for ChipPage - shows the full chip experiments
 */
export function DashboardChipView({
  height = "600px",
  focusOnContent = false,
}: {
  height?: string;
  focusOnContent?: boolean;
}) {
  return (
    <EmbeddedAnalysisView
      title="Chip Experiments"
      icon={<BsCpu />}
      navigateTo="/chip"
      height={height}
    >
      <div
        className={`${focusOnContent ? "dashboard-focus-chip" : ""} overflow-hidden`}
      >
        <ChipPageContent />
      </div>
    </EmbeddedAnalysisView>
  );
}
