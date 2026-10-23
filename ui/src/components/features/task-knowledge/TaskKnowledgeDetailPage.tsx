"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Download } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { downloadTaskKnowledgeArchive } from "@/client/task/task";
import { EvaluationPromptPreview } from "@/components/features/task-knowledge/EvaluationPromptPreview";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { useToast } from "@/components/ui/Toast";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { saveBlob } from "@/lib/utils/download";

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

/** Save the task's knowledge directory as a zip, the starting point of a knowledge draft. */
function DownloadArchiveButton({ taskName }: { taskName: string }) {
  const toast = useToast();
  const [downloading, setDownloading] = useState(false);

  const download = async () => {
    setDownloading(true);
    try {
      const response = await downloadTaskKnowledgeArchive(taskName);
      saveBlob(response.data, `${taskName}.zip`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not download the knowledge"));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <button
      type="button"
      className="btn btn-sm btn-outline gap-1"
      onClick={download}
      disabled={downloading}
      title="task.md, examples and figures as a zip: edit it locally and upload it as a knowledge draft in an AI evaluation"
    >
      {downloading ? (
        <span className="loading loading-spinner loading-xs" />
      ) : (
        <Download size={16} />
      )}
      Download zip
    </button>
  );
}

export function TaskKnowledgeDetailPage({ taskName }: { taskName: string }) {
  const router = useRouter();
  const { data: markdown, isLoading: markdownLoading, error } = useTaskKnowledgeMarkdown(taskName);
  const { data: detail, isLoading: detailLoading } = useTaskKnowledgeDetail(taskName);

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
        <div className="ml-auto">
          <DownloadArchiveButton taskName={taskName} />
        </div>
      </div>
      <MarkdownContent content={markdown} />

      <EvaluationPromptPreview taskName={taskName} exampleCount={detail?.examples?.length ?? 0} />

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
