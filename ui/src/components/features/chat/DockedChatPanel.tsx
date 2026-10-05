"use client";

import { useRouter } from "next/navigation";
import { Maximize2, SquarePen, X } from "lucide-react";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";
import { ChatThread } from "@/components/features/chat/ChatThread";
import {
  RecentChatsMenu,
  SurfaceButton,
  SurfaceTitle,
} from "@/components/features/chat/ChatSurfaceControls";

/** The active chat as a docked column: the app sidebar or a split view inside a modal. */
export function DockedChatPanel({ onClose }: { onClose: () => void }) {
  const { activeSession, createNewSession } = useCopilotChatSessionContext();
  const router = useRouter();

  const openFullPage = () => {
    onClose();
    router.push("/chat");
  };

  return (
    <aside className="h-full w-full flex flex-col bg-base-100" aria-label="AI chat">
      <header className="flex items-start gap-2 px-3 py-2.5 border-b border-base-300/70">
        <SurfaceTitle />
        <div className="flex items-center gap-0.5 shrink-0">
          <SurfaceButton
            label="New chat"
            onClick={() => createNewSession(activeSession?.context ?? null)}
          >
            <SquarePen className="w-3.5 h-3.5" />
          </SurfaceButton>
          <RecentChatsMenu onOpenAll={openFullPage} />
          <SurfaceButton label="Open in full page" onClick={openFullPage}>
            <Maximize2 className="w-3.5 h-3.5" />
          </SurfaceButton>
          <SurfaceButton label="Close" onClick={onClose}>
            <X className="w-4 h-4" />
          </SurfaceButton>
        </div>
      </header>
      <ChatThread variant="panel" />
    </aside>
  );
}
