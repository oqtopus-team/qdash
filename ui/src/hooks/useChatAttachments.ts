"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  attachmentRoom,
  MAX_TOTAL_IMAGE_DATA_LENGTH,
  stageAttachment,
  type StagedAttachment,
} from "@/lib/chatAttachments";

/** Reserve capacity synchronously and stage batches in selection order. */
export function useChatAttachments(sessionId?: string) {
  const current = useRef<StagedAttachment[]>([]);
  const pending = useRef(0);
  const generation = useRef(0);
  const queue = useRef(Promise.resolve());
  const [attachments, setAttachments] = useState<StagedAttachment[]>([]);
  const [isStaging, setIsStaging] = useState(false);
  const [notice, setNotice] = useState("");

  const clear = useCallback(() => {
    generation.current++;
    current.current = [];
    pending.current = 0;
    queue.current = Promise.resolve();
    setAttachments([]);
    setIsStaging(false);
    setNotice("");
  }, []);

  const cancelPending = useCallback(() => {
    generation.current++;
  }, []);

  useEffect(() => {
    clear();
    return cancelPending;
  }, [sessionId, clear, cancelPending]);

  const attach = useCallback((files: File[]) => {
    const selected = files.slice(0, attachmentRoom(current.current.length + pending.current));
    setNotice(selected.length < files.length ? "Up to 4 figures can be attached per message." : "");
    if (!selected.length) return;
    pending.current += selected.length;
    setIsStaging(true);
    const version = generation.current;
    queue.current = queue.current.then(async () => {
      for (const file of selected) {
        if (version !== generation.current) return;
        try {
          const image = await stageAttachment(file);
          if (version !== generation.current) return;
          if (
            current.current.reduce((size, item) => size + item.data.length, 0) + image.data.length >
            MAX_TOTAL_IMAGE_DATA_LENGTH
          ) {
            throw new Error(
              "These images are too large together. Remove an image or choose smaller images.",
            );
          }
          current.current = [...current.current, image];
          setAttachments(current.current);
        } catch (error) {
          if (version === generation.current) {
            setNotice(error instanceof Error ? error.message : "Could not attach this image.");
          }
        } finally {
          if (version === generation.current) {
            pending.current--;
            setIsStaging(pending.current > 0);
          }
        }
      }
    });
  }, []);

  const remove = useCallback((id: string) => {
    current.current = current.current.filter((item) => item.id !== id);
    setAttachments(current.current);
    setNotice("");
  }, []);

  return {
    attachments,
    attach,
    remove,
    clear,
    isStaging,
    notice,
    // A ref closes the gap before React renders the disabled send button.
    isPending: () => pending.current > 0,
  };
}
