"use client";

import { Suspense } from "react";
import { AgentChatPage } from "@/components/features/chat/AgentChatPage";

function ChatPageSkeleton() {
  return (
    <div className="flex h-full animate-pulse">
      <div className="w-64 bg-base-200 border-r border-base-300" />
      <div className="flex-1 bg-base-100" />
    </div>
  );
}

// Sessions come from AgentChatSessionProvider in AppLayout, shared with the
// in-app sidebar and floating window.
export default function ChatPage() {
  return (
    <Suspense fallback={<ChatPageSkeleton />}>
      <AgentChatPage />
    </Suspense>
  );
}
