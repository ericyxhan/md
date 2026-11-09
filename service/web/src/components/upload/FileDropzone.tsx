import { useRef, useState, type DragEvent } from "react";
import { CheckCircle2, FileUp, Loader2, X } from "lucide-react";
import type { FileOut } from "../../lib/types";
import { uploadFile } from "../../lib/api";
import { cn, formatBytes } from "../../lib/utils";
import { ProgressBar } from "../ui/Progress";

export function FileDropzone({
  file,
  onUploaded,
  onRemove,
  accept,
  maxBytes,
  title = "Drop a structure file here",
  hint,
  disabled = false,
}: {
  file?: FileOut | null;
  onUploaded: (file: FileOut) => void;
  onRemove?: () => void;
  accept: string[];
  maxBytes: number;
  title?: string;
  hint?: string;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const acceptLabel = accept.join(", ");

  const validate = (candidate: File): string | null => {
    const suffix = `.${candidate.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!accept.includes(suffix)) {
      return `Unsupported file type. Use ${acceptLabel}.`;
    }
    if (candidate.size > maxBytes) {
      return `File is ${formatBytes(candidate.size)}; the limit is ${formatBytes(maxBytes)}.`;
    }
    if (candidate.size === 0) {
      return "That file is empty.";
    }
    return null;
  };

  const startUpload = async (candidate: File) => {
    const problem = validate(candidate);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setUploading(true);
    setProgress(0);
    try {
      const uploaded = await uploadFile(candidate, setProgress);
      onUploaded(uploaded);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (disabled || uploading) return;
    const candidate = event.dataTransfer.files?.[0];
    if (candidate) void startUpload(candidate);
  };

  if (file) {
    return (
      <div className="rounded-xl border border-brand-200 bg-brand-50/45 p-3.5">
        <div className="flex items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white text-brand-700 shadow-sm ring-1 ring-inset ring-brand-200/70">
            <CheckCircle2 className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium text-ink">
              {file.name}
            </p>
            <p className="mt-0.5 text-[11px] text-muted">
              {formatBytes(file.size_bytes)} · uploaded
            </p>
          </div>
          {onRemove ? (
            <button
              type="button"
              onClick={onRemove}
              className="rounded-md p-1.5 text-muted transition hover:bg-white hover:text-rose-600"
              aria-label={`Remove ${file.name}`}
            >
              <X className="size-4" />
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept={accept.join(",")}
        className="sr-only"
        disabled={disabled || uploading}
        onChange={(event) => {
          const candidate = event.target.files?.[0];
          if (candidate) void startUpload(candidate);
          event.target.value = "";
        }}
      />
      <div
        role="button"
        tabIndex={0}
        aria-disabled={disabled || uploading}
        onClick={() => {
          if (!disabled && !uploading) inputRef.current?.click();
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (!disabled && !uploading) inputRef.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled && !uploading) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-5 py-8 text-center transition",
          dragging
            ? "border-brand-500 bg-brand-50"
            : "border-line-strong bg-surface-muted/60 hover:border-brand-300 hover:bg-brand-50/30",
          (disabled || uploading) && "cursor-default opacity-80",
        )}
      >
        <span
          className={cn(
            "mb-3 flex size-10 items-center justify-center rounded-xl bg-surface text-muted shadow-sm ring-1 ring-inset ring-line",
            dragging && "text-brand-600",
          )}
        >
          {uploading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <FileUp className="size-4" />
          )}
        </span>
        <p className="text-[13px] font-medium text-ink">
          {uploading ? "Uploading…" : title}
        </p>
        <p className="mt-1 text-[11.5px] text-muted">
          {uploading
            ? `${progress}% complete`
            : `or click to browse · ${acceptLabel}`}
        </p>
        {hint ? (
          <p className="mt-1.5 text-[10.5px] text-faint">{hint}</p>
        ) : null}
        {uploading ? (
          <ProgressBar value={progress} className="mt-3 w-48" />
        ) : null}
      </div>
      {error ? (
        <p className="mt-2 text-[12px] font-medium text-rose-600">{error}</p>
      ) : null}
    </div>
  );
}
