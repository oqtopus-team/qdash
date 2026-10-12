"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FolderTree, Image as ImageIcon, Tag } from "lucide-react";
import {
  GitWorkspaceToolbar,
  PullRequestBanner,
} from "@/components/features/files/GitWorkspaceToolbar";
import { useGitWorkspace } from "@/components/features/files/useGitWorkspace";
import { useProject } from "@/contexts/ProjectContext";
import { KNOWLEDGE_WORKSPACE } from "@/lib/fileWorkspace";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { SearchInput } from "@/components/ui/SearchInput";
import { useListTaskKnowledge } from "@/client/task/task";
import type { TaskKnowledgeSummaryResponse } from "@/schemas";

// Category order for display
// calibtasks packages, in calibration order
const CATEGORY_ORDER = [
  "box_setup",
  "system",
  "cw",
  "measurement",
  "one_qubit_coarse",
  "one_qubit_fine",
  "two_qubit",
  "benchmark",
  "analysis",
];

function TaskCard({ item }: { item: TaskKnowledgeSummaryResponse }) {
  const router = useRouter();

  return (
    <div
      onClick={() => router.push(`/knowledge/${item.name}`)}
      className="bg-base-100 rounded-lg border border-base-300 cursor-pointer hover:border-primary/50 transition-colors"
    >
      <div className="p-4">
        <h3 className="text-sm font-semibold font-mono text-primary mb-1">{item.name}</h3>
        <p className="text-sm text-base-content/70 line-clamp-2 mb-2">{item.summary}</p>
        <div className="flex items-center gap-3 text-xs text-base-content/50">
          {(item.example_count ?? 0) > 0 && (
            <span className="flex items-center gap-1" title="Expert-labeled example plots">
              <Tag className="h-3 w-3" />
              {item.example_count} examples
            </span>
          )}
          {(item.figure_count ?? 0) > 0 && (
            <span className="flex items-center gap-1">
              <ImageIcon className="h-3 w-3" />
              {item.figure_count} figures
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function TaskKnowledgePageContent() {
  const { data: resp, isLoading } = useListTaskKnowledge();
  const [searchInput, setSearchInput] = useState("");
  const { canEdit } = useProject();
  const git = useGitWorkspace(KNOWLEDGE_WORKSPACE);

  const categories = resp?.data?.categories ?? {};

  const filtered = useMemo(() => {
    const items = resp?.data?.items ?? [];
    if (!searchInput.trim()) return items;
    const q = searchInput.toLowerCase();
    return items.filter(
      (item) => item.name.toLowerCase().includes(q) || item.summary.toLowerCase().includes(q),
    );
  }, [resp?.data?.items, searchInput]);

  // Group by category
  const grouped = useMemo(() => {
    const map = new Map<string, TaskKnowledgeSummaryResponse[]>();
    for (const item of filtered) {
      const cat = item.category ?? "";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(item);
    }
    // Sort by predefined order
    const sorted = new Map<string, TaskKnowledgeSummaryResponse[]>();
    for (const cat of CATEGORY_ORDER) {
      if (map.has(cat)) {
        sorted.set(cat, map.get(cat)!);
        map.delete(cat);
      }
    }
    // Append any remaining categories
    for (const [cat, catItems] of map) {
      sorted.set(cat, catItems);
    }
    return sorted;
  }, [filtered]);

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Knowledge"
        description="The background of each calibration task and its expert-labeled example plots, laid out like the calibtasks packages. Edits apply here at once; a pull request shares them."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && (
              <Link href={KNOWLEDGE_WORKSPACE.editorPath} className="btn btn-sm btn-ghost gap-1">
                <FolderTree size={16} />
                Browse files
              </Link>
            )}
            {canEdit && (
              <GitWorkspaceToolbar
                status={git.status}
                onPull={git.pull}
                onPush={() => git.push()}
                isPulling={git.isPulling}
                isPushing={git.isPushing}
                pushTitle="Create a pull request with the saved knowledge changes"
              />
            )}
          </div>
        }
      />
      <div className="mb-4 -mx-4 sm:mx-0 sm:rounded-lg sm:overflow-hidden">
        <PullRequestBanner pr={git.prResult} onDismiss={git.dismissPr} />
      </div>

      {/* Search bar */}
      <div className="mb-6">
        <SearchInput value={searchInput} onChange={setSearchInput} placeholder="Search tasks..." />
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No task knowledge found"
          description={
            searchInput
              ? "No tasks match your search."
              : "No task knowledge entries available. Pull the knowledge repository to fetch them."
          }
          emoji="brain"
        />
      ) : (
        <div className="space-y-8">
          {Array.from(grouped.entries()).map(([category, catItems]) => (
            <div key={category}>
              <h2 className="text-base font-semibold mb-3">
                {categories[category] || category || "Other"}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {catItems.map((item) => (
                  <TaskCard key={item.name} item={item} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </PageContainer>
  );
}
