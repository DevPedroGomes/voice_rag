"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

// O backend corta em 10MB (max_file_size_mb no config.py). O cliente
// aceitava 50MB, entao o visitante subia um PDF grande e so descobria o
// limite no erro do servidor.
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ACCEPTED_TYPES = ["application/pdf"];
const SAMPLE_URL = "/samples/aurora-coffee-handbook.pdf";
const SAMPLE_NAME = "aurora-coffee-handbook.pdf";

function validateFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return "Only PDF files are accepted.";
  }
  if (file.size > MAX_FILE_SIZE) {
    return `File is too large. Maximum size is ${MAX_FILE_SIZE / (1024 * 1024)}MB.`;
  }
  return null;
}

interface PDFUploadProps {
  onUpload: (file: File) => Promise<void>;
  isUploading: boolean;
  disabled?: boolean;
}

export function PDFUpload({ onUpload, isUploading, disabled }: PDFUploadProps) {
  const [isDragOver, setIsDragOver] = useState(false);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);

      const files = Array.from(e.dataTransfer.files);
      const file = files[0];
      if (!file) return;

      const error = validateFile(file);
      if (error) {
        toast.error(error);
        return;
      }

      await onUpload(file);
    },
    [onUpload]
  );

  // Quem chega sem PDF a mao nao tinha como ver a demo funcionar: a tela
  // pedia um arquivo e acabava ali. O exemplo e um handbook de suporte
  // ficticio, com secoes em ingles e um FAQ em portugues, que mostra o
  // retrieval multilingue sem depender do arquivo do visitante.
  const handleSampleLoad = useCallback(async () => {
    try {
      const res = await fetch(SAMPLE_URL);
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const file = new File([blob], SAMPLE_NAME, { type: "application/pdf" });
      await onUpload(file);
    } catch {
      toast.error("Could not load the sample document.");
    }
  }, [onUpload]);

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      const error = validateFile(file);
      if (error) {
        toast.error(error);
        e.target.value = "";
        return;
      }

      await onUpload(file);
      e.target.value = "";
    },
    [onUpload]
  );

  return (
    <Card
      className={`p-6 border-2 border-dashed transition-colors ${
        isDragOver
          ? "border-primary bg-primary/5"
          : "border-muted-foreground/25 hover:border-muted-foreground/50"
      } ${disabled ? "opacity-50 pointer-events-none" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragOver(true);
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={handleDrop}
    >
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="p-3 rounded-full bg-muted">
          <svg
            className="w-8 h-8 text-muted-foreground"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
        </div>

        <div>
          <p className="text-sm font-medium">
            {isUploading ? "Processing..." : "Drop your PDF here"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            or click to browse
          </p>
        </div>

        <input
          type="file"
          accept=".pdf"
          className="hidden"
          id="pdf-upload"
          onChange={handleFileSelect}
          disabled={isUploading || disabled}
        />

        <div className="flex flex-col items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            asChild
            disabled={isUploading || disabled}
          >
            <label htmlFor="pdf-upload" className="cursor-pointer">
              {isUploading ? "Uploading..." : "Select PDF"}
            </label>
          </Button>

          <button
            type="button"
            onClick={handleSampleLoad}
            disabled={isUploading || disabled}
            className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed"
          >
            No PDF at hand? Use a sample document
          </button>
        </div>
      </div>
    </Card>
  );
}
