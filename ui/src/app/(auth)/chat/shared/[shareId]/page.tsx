"use client";

import { useParams } from "next/navigation";

import { SharedChatPageContent } from "@/components/features/chat/SharedChatPageContent";

export default function SharedChatPage() {
  const params = useParams<{ shareId: string }>();
  return <SharedChatPageContent shareId={params.shareId} />;
}
