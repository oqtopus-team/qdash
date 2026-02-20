"use client";

import { useState, useCallback } from "react";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

export function useImageUpload() {
  const [isUploading, setIsUploading] = useState(false);

  const uploadImage = useCallback(async (file: File): Promise<string> => {
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await AXIOS_INSTANCE.post<{ url: string }>(
        "/issues/upload-image",
        formData,
      );
      return response.data.url;
    } finally {
      setIsUploading(false);
    }
  }, []);

  return { uploadImage, isUploading };
}
