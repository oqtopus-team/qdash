"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useGetExecution } from "@/client/execution/execution";

/**
 * `/executions/{id}` has no page of its own: the execution page lives under
 * its chip. Links built from an execution id alone (pi-qdash, the API's
 * dispatch responses) land here and are sent on to the real page.
 */
export default function ExecutionRedirectPage() {
  const params = useParams<{ executionId: string }>();
  const executionId = params.executionId;
  const router = useRouter();
  const { data, isError } = useGetExecution(executionId, { query: { retry: false } });
  const chipId = data?.data?.chip_id;

  useEffect(() => {
    if (chipId) {
      router.replace(`/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executionId)}`);
    }
  }, [chipId, executionId, router]);

  if (isError || (data && !chipId)) {
    return (
      <div className="p-8 text-sm text-base-content/60">
        Execution {executionId} was not found in this project.
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 p-8 text-sm text-base-content/60">
      <Loader2 className="w-4 h-4 animate-spin" /> Opening execution {executionId}…
    </div>
  );
}
