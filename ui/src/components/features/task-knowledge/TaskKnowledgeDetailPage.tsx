"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

function useTaskKnowledgeMarkdown(taskName: string) {
  return useQuery({
    queryKey: ["task-knowledge-markdown", taskName],
    queryFn: async () => {
      const resp = await AXIOS_INSTANCE.get(
        `/tasks/${taskName}/knowledge/markdown`,
        { responseType: "text" },
      );
      return resp.data as string;
    },
  });
}

export function TaskKnowledgeDetailPage({ taskName }: { taskName: string }) {
  const router = useRouter();
  const {
    data: markdown,
    isLoading,
    error,
  } = useTaskKnowledgeMarkdown(taskName);

  if (isLoading) {
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
    </div>
  );
}
