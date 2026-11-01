"use client";

import { useMemo } from "react";

import { getListForumLabelsQueryKey, useListForumLabels } from "@/client/forum/forum";
import {
  toForumLabelDefinition,
  type ForumLabelDefinition,
} from "@/components/features/forum/categories";
import { useProject } from "@/contexts/ProjectContext";

/** Load the current project's forum labels, cached separately per project. */
export function useForumLabels() {
  const { projectId } = useProject();
  const { data, isLoading, isError } = useListForumLabels({
    query: {
      queryKey: [...getListForumLabelsQueryKey(), projectId],
      enabled: Boolean(projectId),
      staleTime: 60_000,
    },
  });

  const labels: ForumLabelDefinition[] = useMemo(
    () => data?.data.labels.map(toForumLabelDefinition) ?? [],
    [data?.data.labels],
  );

  return { labels, isLoading, isError };
}
