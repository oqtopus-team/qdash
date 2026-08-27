import { MarkdownContent } from "@/components/ui/MarkdownContent";

import { ForumBlockViewer } from "./ForumBlockEditor";
import { TaskResultLinkPreviews } from "./TaskResultLinkPreviews";
import { extractLinkedTaskResultIds } from "./taskResultLinks";

export function ForumPostContent({
  content,
  contentBlocks,
  markdownClassName,
  markdownPreview = false,
}: {
  content: string;
  contentBlocks?: unknown[] | null;
  markdownClassName?: string;
  markdownPreview?: boolean;
}) {
  const blocks = (contentBlocks ?? []) as Record<string, unknown>[];
  const linkedTaskResultIds = extractLinkedTaskResultIds(content, blocks);

  return (
    <>
      {blocks.length > 0 ? (
        <ForumBlockViewer blocks={blocks} />
      ) : (
        <MarkdownContent
          content={content}
          className={markdownClassName}
          preview={markdownPreview}
        />
      )}
      <TaskResultLinkPreviews taskIds={linkedTaskResultIds} />
    </>
  );
}
