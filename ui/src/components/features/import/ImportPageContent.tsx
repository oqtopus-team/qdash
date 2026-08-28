"use client";

import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";

import { SeedParametersPanel } from "./SeedParametersPanel";

export function ImportPageContent() {
  return (
    <PageContainer maxWidth>
      <div className="space-y-4 sm:space-y-6">
        <PageHeader
          title="Calibration Database"
          description="View the latest calibration values for each qubit and apply updates from YAML"
        />
        <SeedParametersPanel />
      </div>
    </PageContainer>
  );
}
