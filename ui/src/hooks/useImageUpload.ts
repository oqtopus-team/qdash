"use client";

import { useState, useCallback } from "react";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

const UPLOAD_PATH = "/forum/upload-image";

export function useImageUpload(_target: "forum" = "forum") {
  const [isUploading, setIsUploading] = useState(false);

  const uploadImage = useCallback(async (file: File): Promise<string> => {
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await AXIOS_INSTANCE.post<{ url: string }>(UPLOAD_PATH, formData);
      return response.data.url;
    } finally {
      setIsUploading(false);
    }
  }, []);

  return { uploadImage, isUploading };
}
