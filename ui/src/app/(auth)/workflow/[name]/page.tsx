import { Suspense } from "react";

import { WorkflowEditorPageContent } from "@/components/features/flow/WorkflowEditorPageContent";
import { WorkflowEditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function EditFlowPage() {
  // The editor reads `?space=` with useSearchParams, which needs a Suspense boundary.
  return (
    <Suspense fallback={<WorkflowEditorPageSkeleton />}>
      <WorkflowEditorPageContent />
    </Suspense>
  );
}
