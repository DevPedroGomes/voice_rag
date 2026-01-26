"use client";

import { useState, useCallback } from "react";
import type { SessionDocument } from "@/types/api";
import { uploadDocument, deleteDocument as apiDeleteDocument } from "@/lib/api-client";

interface UseDocumentsReturn {
  isUploading: boolean;
  uploadError: string | null;
  upload: (sessionId: string, file: File) => Promise<SessionDocument | null>;
  deleteDocument: (sessionId: string, documentId: string) => Promise<boolean>;
}

export function useDocuments(): UseDocumentsReturn {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const upload = useCallback(
    async (sessionId: string, file: File): Promise<SessionDocument | null> => {
      setIsUploading(true);
      setUploadError(null);

      try {
        const result = await uploadDocument(sessionId, file);
        return {
          document_id: result.document_id,
          file_name: result.file_name,
          page_count: result.page_count,
          chunk_count: result.chunk_count,
          processed_at: result.processed_at,
        };
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        setUploadError(message);
        return null;
      } finally {
        setIsUploading(false);
      }
    },
    []
  );

  const deleteDoc = useCallback(
    async (sessionId: string, documentId: string): Promise<boolean> => {
      try {
        await apiDeleteDocument(sessionId, documentId);
        return true;
      } catch {
        return false;
      }
    },
    []
  );

  return {
    isUploading,
    uploadError,
    upload,
    deleteDocument: deleteDoc,
  };
}
