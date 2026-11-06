"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/** Legacy `/forum/posts/{id}` links go to the post page at `/forum/{id}`. */
export default function ForumPostRedirectPage() {
  const params = useParams<{ postId: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/forum/${encodeURIComponent(params.postId)}`);
  }, [params.postId, router]);
  return null;
}
