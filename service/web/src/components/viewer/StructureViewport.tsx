import { useEffect, useRef, useState } from "react";
import { Viewer } from "molstar/lib/apps/viewer/app.js";
import "molstar/build/viewer/molstar.css";
import { AlertTriangle, RotateCcw } from "lucide-react";
import {
  cn,
  type ViewerStructureFormat,
  structureFormatFromContentType,
} from "../../lib/utils";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/EmptyState";

export interface StructureViewportProps {
  /** URL of a small, browser-sized structure — a derived view or a raw upload. */
  url: string;
  /** Mol* structure format for the URL (defaults to PDB). */
  format?: ViewerStructureFormat;
  /** Label Mol* shows for the loaded structure. */
  label?: string;
  className?: string;
}

/**
 * Mol* viewer wrapper — the only file in the app that imports molstar.
 *
 * Always mount through `React.lazy(() => import("./StructureViewport"))` so
 * the heavy viewer chunk is fetched on demand and never blocks first paint.
 * The viewer degrades to a message (with a download fallback) when WebGL is
 * unavailable or the structure fails to load; the surrounding UI is untouched.
 */
export default function StructureViewport({
  url,
  format = "pdb",
  label,
  className,
}: StructureViewportProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    let viewer: Viewer | null = null;
    setPhase("loading");
    setError(null);

    Viewer.create(host, {
      // Minimal, calm layout: viewport plus its overlay buttons only.
      layoutIsExpanded: false,
      layoutShowControls: false,
      layoutShowLog: false,
      layoutShowLeftPanel: false,
      // No trajectory loaded in V1; playback arrives with stage views.
      viewportShowAnimation: false,
      viewportShowTrajectoryControls: false,
      // Click-to-inspect stays available; selection-driven editing is V2.
      viewportShowSelectionMode: true,
      viewportBackgroundColor: "#ffffff",
    })
      .then(async (instance) => {
        if (cancelled) {
          instance.dispose();
          return;
        }
        viewer = instance;
        try {
          // Ask for the headers first when the server supports it.  Mol*
          // does not fail on a response that is not a structure: it parses
          // the body, finds no atoms and leaves an empty scene behind,
          // which reads as a blank viewer.  The check also tells us the
          // format of a derived preview, which is always served as PDB.
          const response = await fetch(url, { method: "HEAD" }).catch(
            () => null,
          );
          let resolvedFormat = format;
          if (response) {
            if (response.ok) {
              resolvedFormat =
                structureFormatFromContentType(
                  response.headers.get("content-type") ?? "",
                ) ?? format;
            } else if (response.status !== 405 && response.status !== 501) {
              throw new Error(
                `This structure is not available for preview (HTTP ${response.status}).`,
              );
            }
            // 405 or 501: the endpoint does not answer HEAD, so load it the
            // usual way and let Mol* report any problem.
          }

          await instance.loadStructureFromUrl(
            url,
            resolvedFormat,
            false,
            label ? { label } : undefined,
          );
          if (!cancelled) setPhase("ready");
        } catch (cause) {
          if (cancelled) return;
          setPhase("error");
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setPhase("error");
        setError(
          cause instanceof Error
            ? cause.message
            : "This browser cannot create a 3D canvas (WebGL)",
        );
      });

    return () => {
      cancelled = true;
      viewer?.dispose();
    };
  }, [url, format, label, attempt]);

  return (
    <div
      className={cn("relative h-full w-full overflow-hidden rounded-b-xl", className)}
      data-testid="structure-viewport"
    >
      <div ref={hostRef} className="absolute inset-0" />

      {phase === "loading" ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-surface/60">
          <div className="flex items-center gap-2 text-[12.5px] text-muted">
            <Spinner /> Preparing structure
          </div>
        </div>
      ) : null}

      {phase === "error" ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-surface p-6 text-center">
          <AlertTriangle className="size-5 text-amber-600" />
          <p className="max-w-sm text-[12.5px] leading-relaxed text-ink-soft">
            The structure could not be rendered
            {error ? ` (${error})` : ""}. The raw artifacts remain available in
            the Artifacts tab.
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              leadingIcon={<RotateCcw className="size-3.5" />}
              onClick={() => setAttempt((value) => value + 1)}
            >
              Try again
            </Button>
            <a
              href={url}
              className="text-[12px] font-medium text-brand-700 underline-offset-2 hover:underline"
            >
              Download instead
            </a>
          </div>
        </div>
      ) : null}
    </div>
  );
}
