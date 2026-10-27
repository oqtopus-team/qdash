"use client";

import type { ChipProvisioningResult, ChipPublishStatus } from "@/schemas";

const PUBLISH_BADGE: Record<string, { className: string; label: string }> = {
  published: { className: "badge-success", label: "Published" },
  recorded: { className: "badge-warning", label: "Recorded locally" },
  failed: { className: "badge-error", label: "Publish failed" },
  skipped: { className: "badge-ghost", label: "Nothing to publish" },
};

/** Badge for the outcome of writing generated files to the configuration repository. */
export function PublishStatusBadge({ publish }: { publish: ChipPublishStatus | undefined }) {
  if (!publish) return null;
  const badge = PUBLISH_BADGE[publish.status] ?? {
    className: "badge-ghost",
    label: publish.status,
  };
  return (
    <span className={`badge badge-sm ${badge.className}`} title={publish.message ?? undefined}>
      {badge.label}
      {publish.commit ? ` @ ${publish.commit}` : ""}
    </span>
  );
}

/**
 * What chip creation or a System addition wrote: Systems, source of the
 * wiring, repository outcome and warnings. The warnings are the part to act on.
 */
export function ProvisioningResultPanel({
  result,
  systemIds,
  files,
  publish,
  warnings,
}: {
  result?: ChipProvisioningResult | null;
  systemIds?: string[];
  files?: string[];
  publish?: ChipPublishStatus;
  warnings?: string[];
}) {
  const ids = systemIds ?? result?.system_ids ?? [];
  const paths = files ?? result?.files ?? [];
  const publishStatus = publish ?? result?.publish;
  const warningList = warnings ?? result?.warnings ?? [];

  if (result && !result.provisioned) {
    return (
      <div className="alert alert-info text-sm" role="status">
        <span>
          Only the database record was created ({result.layout} layout). Copy the configuration
          directory yourself before the first run.
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm" data-testid="provisioning-result">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        {ids.length > 0 && (
          <>
            <dt className="text-base-content/60">Systems</dt>
            <dd className="flex flex-wrap gap-1">
              {ids.map((id) => (
                <span key={id} className="badge badge-outline badge-sm font-mono">
                  {id}
                </span>
              ))}
            </dd>
          </>
        )}
        {result?.inherited_from && (
          <>
            <dt className="text-base-content/60">Wiring from</dt>
            <dd className="font-mono">{result.inherited_from}</dd>
          </>
        )}
        {publishStatus && (
          <>
            <dt className="text-base-content/60">Repository</dt>
            <dd className="flex flex-wrap items-center gap-2">
              <PublishStatusBadge publish={publishStatus} />
              {publishStatus.message &&
                (publishStatus.status === "failed" || publishStatus.status === "recorded") && (
                  <span className="text-base-content/70">{publishStatus.message}</span>
                )}
            </dd>
          </>
        )}
      </dl>
      {warningList.length > 0 && (
        <div className="alert alert-warning text-sm" role="alert">
          <ul className="list-disc pl-4">
            {warningList.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      {paths.length > 0 && (
        <details className="collapse collapse-arrow bg-base-200">
          <summary className="collapse-title min-h-0 py-2 text-sm">
            {paths.length} {paths.length === 1 ? "file" : "files"} written
          </summary>
          <div className="collapse-content">
            <ul className="font-mono text-xs space-y-0.5">
              {paths.map((path) => (
                <li key={path}>{path}</li>
              ))}
            </ul>
          </div>
        </details>
      )}
    </div>
  );
}
