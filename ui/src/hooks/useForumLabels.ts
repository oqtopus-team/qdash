"use client";

import { useMemo } from "react";

import { useListForumLabels } from "@/client/forum/forum";
import { toForumLabelDefinition, type ForumLabelDefinition } from "@/components/features/forum/categories";

export function useForumLabels() {
  const { data, isLoading, isError } = useListForumLabels({
    query: { staleTime: 60_000 },
  });

  const labels: ForumLabelDefinition[] = useMemo(
    () => data?.data.labels.map(toForumLabelDefinition) ?? [],
    [data?.data.labels],
  );

  return { labels, isLoading, isError };
}
