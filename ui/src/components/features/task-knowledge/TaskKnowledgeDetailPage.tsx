"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, Image as ImageIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

type KnowledgeImage = {
  alt_text: string;
  relative_path: string;
  base64_data?: string;
};

type KnowledgeCase = {
  title: string;
  date?: string;
  severity?: string;
  human_review_decision?: string;
  boundary_criteria?: string;
  lesson_learned?: string[];
  images?: KnowledgeImage[];
};

type TaskKnowledgeDetail = {
  review_markdown?: string;
  review_images?: KnowledgeImage[];
  cases?: KnowledgeCase[];
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
          onClick={() => router.push("/task-knowledge")}
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
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => router.push("/task-knowledge")}
          className="btn btn-ghost btn-sm btn-square"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h1 className="text-xl font-bold font-mono">{taskName}</h1>
      </div>
      <MarkdownContent content={markdown} />

      {detail?.review_markdown?.trim() && (
        <section className="mt-10">
          <div className="mb-3">
            <h2 className="text-lg font-semibold">AI Review Guide</h2>
            <p className="text-sm text-base-content/60">
              Operational guidance used for automatic review decisions.
            </p>
          </div>
          <div className="rounded-xl border border-base-300 bg-base-100 p-5">
            <MarkdownContent content={detail.review_markdown} />
          </div>
        </section>
      )}

      {(detail?.cases?.length ?? 0) > 0 && (
        <section className="mt-10">
          <div className="mb-3">
            <h2 className="text-lg font-semibold">Cases</h2>
            <p className="text-sm text-base-content/60">
              Operational cases and counterexamples linked to this task.
            </p>
          </div>
          <div className="space-y-4">
            {detail?.cases?.map((knowledgeCase) => (
              <article
                key={`${knowledgeCase.title}-${knowledgeCase.date ?? ""}`}
                className="rounded-xl border border-base-300 bg-base-100 p-5"
              >
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <h3 className="text-base font-semibold">{knowledgeCase.title}</h3>
                  {knowledgeCase.severity && (
                    <span className="badge badge-outline badge-sm">{knowledgeCase.severity}</span>
                  )}
                  {knowledgeCase.date && (
                    <span className="text-xs text-base-content/50">{knowledgeCase.date}</span>
                  )}
                </div>

                {knowledgeCase.human_review_decision && (
                  <div className="mb-3">
                    <div className="text-xs font-medium uppercase tracking-wide text-base-content/50 mb-1">
                      Human Review Decision
                    </div>
                    <p className="text-sm text-base-content/80">
                      {knowledgeCase.human_review_decision}
                    </p>
                  </div>
                )}

                {knowledgeCase.boundary_criteria && (
                  <div className="mb-3">
                    <div className="text-xs font-medium uppercase tracking-wide text-base-content/50 mb-1">
                      Boundary Criteria
                    </div>
                    <p className="text-sm text-base-content/80">
                      {knowledgeCase.boundary_criteria}
                    </p>
                  </div>
                )}

                {(knowledgeCase.lesson_learned?.length ?? 0) > 0 && (
                  <div className="mb-3">
                    <div className="text-xs font-medium uppercase tracking-wide text-base-content/50 mb-1">
                      Lessons
                    </div>
                    <ul className="list-disc pl-5 text-sm text-base-content/80 space-y-1">
                      {knowledgeCase.lesson_learned?.map((lesson) => (
                        <li key={lesson}>{lesson}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {(knowledgeCase.images?.length ?? 0) > 0 && (
                  <div>
                    <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-base-content/50 mb-2">
                      <ImageIcon className="h-3.5 w-3.5" />
                      Case Figures
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      {knowledgeCase.images?.map((image) => (
                        <figure
                          key={`${knowledgeCase.title}-${image.relative_path}`}
                          className="rounded-lg border border-base-300 bg-base-200/40 p-3"
                        >
                          {image.base64_data ? (
                            /* eslint-disable-next-line @next/next/no-img-element -- task knowledge images are API-provided base64 assets */
                            <img
                              src={`data:image/png;base64,${image.base64_data}`}
                              alt={image.alt_text}
                              className="w-full h-auto rounded"
                            />
                          ) : (
                            <div className="flex items-center justify-center rounded border border-dashed border-base-300 bg-base-100 px-3 py-8 text-sm text-base-content/50">
                              Image asset unavailable
                            </div>
                          )}
                          <figcaption className="mt-2 text-xs text-base-content/60">
                            {image.alt_text}
                          </figcaption>
                        </figure>
                      ))}
                    </div>
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
