import { Suspense } from "react";
import { useCapabilities } from "../../lib/queries";
import type { ViewerStructureFormat } from "../../lib/utils";
import { EmptyState } from "../ui/EmptyState";
import { LazyStructureViewport } from "./lazy";

export interface StructurePreviewProps {
  /** URL of the structure to render. */
  url: string;
  /** Mol* format of the structure; the server may serve a different one. */
  format?: ViewerStructureFormat;
  /** Label shown for the structure. */
  label?: string;
  /** Size of the original file, used to explain a derived preview. */
  sourceSizeBytes?: number;
  /** Height of the viewer box. */
  className?: string;
}

/**
 * A structure in the Mol* viewer, with an explanation when the server had
 * to derive a smaller preview.
 *
 * A membrane-embedded or solvated system is far too large to send to a
 * browser raw.  The server derives a preview with the solvent removed, and
 * this says so, because the picture is then not the whole file.
 */
export function StructurePreview({
  url,
  format,
  label,
  sourceSizeBytes,
  className,
}: StructurePreviewProps) {
  const capabilities = useCapabilities();
  const limit = capabilities.data?.limits.max_preview_bytes ?? 0;
  const derived = limit > 0 && (sourceSizeBytes ?? 0) > limit;

  return (
    <>
      <div className={className}>
        <Suspense
          fallback={
            <EmptyState
              icon={
                <div className="flex items-center gap-2 text-[12px] text-muted">
                  <span className="animate-pulse size-3 rounded-full bg-brand-200" />
                  Rendering structure…
                </div>
              }
              title="Loading structure"
              description="The viewer chunk loads once per session."
              className="absolute inset-0 z-10 flex-col"
            />
          }
        >
          <LazyStructureViewport
            url={url}
            format={format ?? undefined}
            label={label}
          />
        </Suspense>
      </div>
      {derived ? (
        <p className="text-[11px] leading-relaxed text-muted">
          Solvent and ions were removed so this structure fits in the browser.
          The complete file is what the simulation uses.
        </p>
      ) : null}
    </>
  );
}
