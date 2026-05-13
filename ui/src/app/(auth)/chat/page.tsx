"use client";

import { Suspense } from "react";
import { CopilotChatPage } from "@/components/features/chat/CopilotChatPage";
import { CopilotChatSessionProvider } from "@/contexts/CopilotChatSessionContext";

function ChatPageSkeleton() {
  return (
    <div className="flex h-full animate-pulse">
      <div className="w-64 bg-base-200 border-r border-base-300" />
      <div className="flex-1 bg-base-100" />
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<ChatPageSkeleton />}>
      <CopilotChatSessionProvider>
        <CopilotChatPage />
      </CopilotChatSessionProvider>
    </Suspense>
  );
}
