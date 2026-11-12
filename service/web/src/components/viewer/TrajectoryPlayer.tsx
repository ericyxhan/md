import { useEffect, useRef, useState } from "react";
import { Viewer } from "molstar/lib/apps/viewer/app.js";
import "molstar/build/viewer/molstar.css";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { cn } from "../../lib/utils";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/EmptyState";

export interface TrajectoryPlayerProps {
  /** Topology (PDB) URL — from view.structure.url */
  pdbUrl: string;
  /** Trajectory (DCD) URL — from view.trajectory.url */
  dcdUrl: string;
  /** Label Mol* shows for the loaded structure. */
  label?: string;
  className?: string;
}

/**
 * Mol* trajectory player — loads a PDB topology plus a DCD trajectory via
 * Mol*'s ``loadTrajectory`` API and exposes Mol*'s built-in playback controls
 * (play/pause, frame scrubber, speed, loop, interpolation).
 *
 * Always mount through `React.lazy(() => import("./TrajectoryPlayer"))` so
 * the heavy viewer chunk is fetched on demand.
 */
export default function TrajectoryPlayer({
  pdbUrl,
  dcdUrl,
  label,
  className,
}: TrajectoryPlayerProps) {
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
      // Trajectory playback UI is built in.
      viewportShowAnimation: true,
      viewportShowTrajectoryControls: true,
      // Click-to-inspect stays available.
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
          // Load topology (PDB) + trajectory (DCD) together via Mol*'s
          // loadTrajectory API.  Atom order must match exactly between the
          // two files — guaranteed because both are produced by the same
          // mdtraj.atom_slice call in the worker.
          await instance.loadTrajectory({
            model: {
              kind: "model-url",
              url: pdbUrl,
              format: "pdb",
            },
            coordinates: {
              kind: "coordinates-url",
              url: dcdUrl,
              format: "dcd",
              isBinary: true,
            },
            modelLabel: label ?? dcdUrl.split("/").pop() ?? "trajectory",
          });
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
  }, [pdbUrl, dcdUrl, label, attempt]);

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden rounded-b-xl",
        className
      )}
      data-testid="trajectory-player"
    >
      <div ref={hostRef} className="absolute inset-0" />

      {phase === "loading" ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-surface/60">
          <div className="flex items-center gap-2 text-[12.5px] text-muted">
            <Spinner /> Loading trajectory
          </div>
        </div>
      ) : null}

      {phase === "error" ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-surface p-6 text-center">
          <AlertTriangle className="size-5 text-amber-600" />
          <p className="max-w-sm text-[12.5px] leading-relaxed text-ink-soft">
            The trajectory could not be rendered
            {error ? ` (${error})` : ""}. The raw artifacts remain available
            in the Artifacts tab.
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
              href={pdbUrl}
              className="text-[12px] font-medium text-brand-700 underline-offset-2 hover:underline"
            >
              Download PDB instead
            </a>
          </div>
        </div>
      ) : null}
    </div>
  );
}
