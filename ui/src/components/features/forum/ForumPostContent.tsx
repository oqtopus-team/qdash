import { MarkdownContent } from "@/components/ui/MarkdownContent";

import { ForumBlockViewer } from "./ForumBlockEditor";
import { TaskResultLinkPreviews } from "./TaskResultLinkPreviews";
import { extractLinkedTaskResultIds } from "./taskResultLinks";

export function ForumPostContent({
  content,
  contentBlocks,
  markdownClassName,
  markdownPreview = false,
  aboutTaskId = null,
}: {
  content: string;
  contentBlocks?: unknown[] | null;
  markdownClassName?: string;
  markdownPreview?: boolean;
  /** The task result the thread is about; shown before the text so its state is in view. */
  aboutTaskId?: string | null;
}) {
  const blocks = (contentBlocks ?? []) as Record<string, unknown>[];
  const linkedTaskResultIds = extractLinkedTaskResultIds(content, blocks).filter(
    (id) => id !== aboutTaskId,
  );

  return (
    <>
      {aboutTaskId && (
        <TaskResultLinkPreviews
          taskIds={[aboutTaskId]}
          heading="About this task result"
          className="mb-4 space-y-2"
        />
      )}
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
