"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, FileCode2, GitCompareArrows, Pencil } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getListTaskKnowledgeQueryKey } from "@/client/task/task";
import {
  GitWorkspaceToolbar,
  PullRequestBanner,
} from "@/components/features/files/GitWorkspaceToolbar";
import { useGitWorkspace } from "@/components/features/files/useGitWorkspace";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FileDiffReviewDialog } from "@/components/ui/FileDiffReviewDialog";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { useToast } from "@/components/ui/Toast";
import { useProject } from "@/contexts/ProjectContext";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";
import { KNOWLEDGE_WORKSPACE, knowledgeIndexPath, workspaceQueryKeys } from "@/lib/fileWorkspace";
import { getApiErrorMessage } from "@/lib/utils/apiError";

type KnowledgeFigure = {
  alt: string;
  path: string;
  base64_data?: string;
  mime_type?: string;
};

type KnowledgeExample = {
  id: string;
  title: string;
  date?: string;
  chip?: string;
  qid?: string;
  outcome: string;
  fit_quality?: string;
  verdict?: string;
  source?: string;
  status?: string;
  suggested_range?: string;
  parameters?: string;
  figures?: KnowledgeFigure[];
  diagnosis?: string;
};

type TaskKnowledgeDetail = {
  category?: string;
  examples?: KnowledgeExample[];
};

const OUTCOME_BADGE: Record<string, string> = {
  expected: "badge-success",
  suboptimal: "badge-warning",
  anomalous: "badge-error",
  apparatus: "badge-neutral",
};

function useTaskKnowledgeMarkdown(taskName: string) {
  return useQuery({
    queryKey: ["task-knowledge-markdown", taskName],
    queryFn: async () => {
      const resp = await AXIOS_INSTANCE.get(`/tasks/${taskName}/knowledge/markdown`, {
        responseType: "text",
      });
      return resp.data as string;
    },
  });
}

function useTaskKnowledgeDetail(taskName: string) {
  return useQuery({
    queryKey: ["task-knowledge-detail", taskName],
    queryFn: async () => {
      const resp = await AXIOS_INSTANCE.get(`/tasks/${taskName}/knowledge`);
      return resp.data as TaskKnowledgeDetail;
    },
  });
}

/**
 * Editor of the task's ``index.md`` in the knowledge repository. Saving applies
 * the change to this QDash at once; the git toolbar turns it into a PR.
 */
function KnowledgeIndexEditor({
  taskName,
  path,
  onClose,
}: {
  taskName: string;
  path: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState<string | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);

  const { data: file, isLoading } = useQuery({
    queryKey: workspaceQueryKeys.content(KNOWLEDGE_WORKSPACE, path),
    queryFn: () => KNOWLEDGE_WORKSPACE.getContent(path),
  });
  useEffect(() => {
    if (file && draft === null) setDraft(file.content);
  }, [file, draft]);

  const saveMutation = useMutation({
    mutationFn: (content: string) => KNOWLEDGE_WORKSPACE.saveContent(path, content),
    onSuccess: () => {
      toast.success(`Saved ${taskName}; it is in effect here. Create a PR to share it.`);
      queryClient.invalidateQueries({ queryKey: ["task-knowledge-markdown", taskName] });
      queryClient.invalidateQueries({ queryKey: ["task-knowledge-detail", taskName] });
      queryClient.invalidateQueries({ queryKey: getListTaskKnowledgeQueryKey() });
      queryClient.invalidateQueries({
        queryKey: workspaceQueryKeys.content(KNOWLEDGE_WORKSPACE, path),
      });
      queryClient.invalidateQueries({
        queryKey: workspaceQueryKeys.gitStatus(KNOWLEDGE_WORKSPACE),
      });
      setDraft(null);
      onClose();
    },
    onError: (error: Error) => {
      toast.error(`Failed to save: ${getApiErrorMessage(error, "Unknown error")}`);
    },
  });

  const dirty = file !== undefined && draft !== null && draft !== file.content;
  const requestClose = () => (dirty ? setDiscardOpen(true) : onClose());

  if (isLoading || draft === null) {
    return (
      <div className="flex justify-center py-8">
        <span className="loading loading-spinner loading-md"></span>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-base-300 bg-base-100 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold">Edit knowledge</div>
          <div className="truncate font-mono text-xs text-base-content/50">{path}</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-sm btn-ghost gap-1"
            onClick={() => setReviewOpen(true)}
            disabled={!file?.is_saved_change || dirty}
            title={
              dirty ? "Save before reviewing" : "Review the saved changes against the last commit"
            }
          >
            <GitCompareArrows size={16} />
            Review
          </button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={requestClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={() => saveMutation.mutate(draft)}
            disabled={!dirty || saveMutation.isPending}
          >
            {saveMutation.isPending ? (
              <span className="loading loading-spinner loading-xs"></span>
            ) : (
              "Save"
            )}
          </button>
        </div>
      </div>
      <p className="mb-3 text-xs text-base-content/60">
        The first heading is the task name. Relative image paths resolve after saving; add images
        with the file browser.
      </p>
      <MarkdownEditor
        value={draft}
        onChange={setDraft}
        rows={28}
        placeholder="Task knowledge in Markdown"
        disabled={saveMutation.isPending}
      />
      {file && (
        <FileDiffReviewDialog
          filename={path}
          newContent={file.content}
          oldContent={file.base_content}
          onClose={() => setReviewOpen(false)}
          open={reviewOpen}
        />
      )}
      <ConfirmDialog
        open={discardOpen}
        title="Discard unsaved changes?"
        description="Your edits to this task's knowledge will be lost."
        confirmLabel="Discard"
        onConfirm={() => {
          setDiscardOpen(false);
          onClose();
        }}
        onOpenChange={setDiscardOpen}
        destructive
      />
    </div>
  );
}

export function TaskKnowledgeDetailPage({ taskName }: { taskName: string }) {
  const router = useRouter();
  const { canEdit } = useProject();
  const [editing, setEditing] = useState(false);
  const { data: markdown, isLoading: markdownLoading, error } = useTaskKnowledgeMarkdown(taskName);
  const { data: detail, isLoading: detailLoading } = useTaskKnowledgeDetail(taskName);
  const git = useGitWorkspace(KNOWLEDGE_WORKSPACE);
  const indexPath = detail?.category ? knowledgeIndexPath(detail.category, taskName) : null;

  if (markdownLoading || detailLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error || !markdown) {
    return (
      <div className="p-6">
        <button
          onClick={() => router.push("/knowledge")}
          className="btn btn-ghost btn-sm gap-1 mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <div className="text-center py-16 text-base-content/50">
          Knowledge not found for &quot;{taskName}&quot;
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <button
          onClick={() => router.push("/knowledge")}
          className="btn btn-ghost btn-sm btn-square"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h1 className="text-xl font-bold font-mono">{taskName}</h1>
        {canEdit && indexPath && (
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Link
              href={`${KNOWLEDGE_WORKSPACE.editorPath}?path=${encodeURIComponent(indexPath)}`}
              className="btn btn-sm btn-ghost gap-1"
              title="Open this task's folder in the file browser (examples, figures)"
            >
              <FileCode2 size={16} />
              Files
            </Link>
            <button
              type="button"
              className={`btn btn-sm gap-1 ${editing ? "btn-warning" : "btn-outline"}`}
              onClick={() => setEditing(true)}
              disabled={editing}
            >
              <Pencil size={16} />
              Edit
            </button>
            <GitWorkspaceToolbar
              status={git.status}
              onPull={git.pull}
              onPush={() => git.push(`Update knowledge for ${taskName}`)}
              isPulling={git.isPulling}
              isPushing={git.isPushing}
              pushTitle="Create a pull request with the saved knowledge changes"
            />
          </div>
        )}
      </div>
      <PullRequestBanner pr={git.prResult} onDismiss={git.dismissPr} />
      {editing && indexPath ? (
        <KnowledgeIndexEditor
          taskName={taskName}
          path={indexPath}
          onClose={() => setEditing(false)}
        />
      ) : (
        <MarkdownContent content={markdown} />
      )}

      {(detail?.examples?.length ?? 0) > 0 && (
        <section className="mt-10">
          <div className="mb-3">
            <h2 className="text-lg font-semibold">Labeled examples</h2>
            <p className="text-sm text-base-content/60">
              Plots with the diagnosis an expert validated. The evaluation model sees them as
              demonstrations.
            </p>
          </div>
          <div className="space-y-4">
            {detail?.examples?.map((example) => (
              <article
                key={example.id}
                className="rounded-xl border border-base-300 bg-base-100 p-5"
              >
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <h3 className="text-base font-semibold">{example.title}</h3>
                  <span
                    className={`badge badge-sm ${OUTCOME_BADGE[example.outcome] ?? "badge-ghost"}`}
                  >
                    {example.outcome}
                  </span>
                  {example.fit_quality && (
                    <span className="badge badge-outline badge-sm">fit {example.fit_quality}</span>
                  )}
                  {example.verdict && (
                    <span className="badge badge-outline badge-sm">{example.verdict}</span>
                  )}
                  {example.status && (
                    <span
                      className="badge badge-outline badge-sm font-mono"
                      title="Status code the example demonstrates"
                    >
                      {example.status}
                    </span>
                  )}
                  {example.suggested_range && (
                    <span className="text-xs text-base-content/60">
                      range {example.suggested_range}
                    </span>
                  )}
                  {(example.chip || example.qid) && (
                    <span className="text-xs text-base-content/50">
                      {[example.chip, example.qid && `Q${example.qid}`].filter(Boolean).join(" · ")}
                    </span>
                  )}
                  {example.date && (
                    <span className="text-xs text-base-content/50">{example.date}</span>
                  )}
                </div>
                {(example.figures?.length ?? 0) > 0 && (
                  <div className="grid gap-3 md:grid-cols-2 mb-3">
                    {example.figures?.map((figure) => (
                      <figure
                        key={figure.path}
                        className="rounded-lg border border-base-300 bg-base-200/40 p-3"
                      >
                        {figure.base64_data ? (
                          /* eslint-disable-next-line @next/next/no-img-element -- knowledge figures are API-provided base64 assets */
                          <img
                            src={`data:${figure.mime_type || "image/png"};base64,${figure.base64_data}`}
                            alt={figure.alt}
                            className="w-full h-auto rounded"
                          />
                        ) : (
                          <div className="flex items-center justify-center rounded border border-dashed border-base-300 bg-base-100 px-3 py-8 text-sm text-base-content/50">
                            Figure unavailable
                          </div>
                        )}
                        <figcaption className="mt-2 text-xs text-base-content/60">
                          {figure.alt || figure.path}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                )}
                {example.diagnosis && <MarkdownContent content={example.diagnosis} />}
                {example.parameters && (
                  <p className="mt-2 text-xs text-base-content/60">
                    Parameters read from the plot:{" "}
                    <code className="font-mono">{example.parameters}</code>
                  </p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
