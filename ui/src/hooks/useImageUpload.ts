"use client";

import { useState, useCallback } from "react";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

type ImageUploadTarget = "issues" | "forum";

const UPLOAD_PATHS: Record<ImageUploadTarget, string> = {
  issues: "/issues/upload-image",
  forum: "/forum/upload-image",
};

export function useImageUpload(target: ImageUploadTarget = "issues") {
  const [isUploading, setIsUploading] = useState(false);

  const uploadImage = useCallback(async (file: File): Promise<string> => {
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await AXIOS_INSTANCE.post<{ url: string }>(
        UPLOAD_PATHS[target],
        formData,
      );
      return response.data.url;
    } finally {
      setIsUploading(false);
    }
  }, [target]);

  return { uploadImage, isUploading };
}
