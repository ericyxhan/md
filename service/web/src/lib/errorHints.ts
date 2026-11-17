export type ErrorHint = {
  title: string;
  likelyCauses: string[];
  fixes: string[];
  docsAnchor?: string;
};

/** Heuristic mapping from job error code/message to actionable guidance. */
export function classifyJobError(code?: string, message?: string): ErrorHint | null {
  const c = (code || "").toLowerCase();
  const m = (message || "").toLowerCase();
  const blob = `${c}\n${m}`;

  // Known structured codes (backend/worker)
  if (c === "worker_lost") {
    return {
      title: "Worker connection lost",
      likelyCauses: ["The GPU worker stopped responding or the job lease expired."],
      fixes: [
        "Retry the job. If this happens repeatedly, check worker health and GPU/host stability.",
        "Ensure the worker container/service is running and has GPU access.",
      ],
    };
  }
  if (c === "simulate_failed" || c === "stage_failed" || c === "prep_failed" || c === "prep_worker_error") {
    // fall through to message heuristics but with a better default title
  }
  if (c === "stage_incomplete") {
    return {
      title: "Stage did not complete",
      likelyCauses: ["A simulation stage ended without producing the expected outputs."],
      fixes: [
        "Check the Logs tab for the failing stage and the last error lines.",
        "Retry the job; if it persists, try a shorter test run to isolate the issue.",
      ],
    };
  }
  if (c === "canceled" || c === "cancelled") {
    return {
      title: "Run canceled",
      likelyCauses: ["You or an administrator stopped the job."],
      fixes: ["Use Retry to start again, or adjust inputs/settings before retrying."],
    };
  }

  if (blob.includes("oom") || blob.includes("out of memory") || blob.includes("cuda out of memory")) {
    return {
      title: "Out of memory (GPU/RAM)",
      likelyCauses: [
        "System is too large for the available GPU memory.",
        "Too many atoms, large box, or memory-intensive settings.",
      ],
      fixes: [
        "Reduce system size or use a smaller/lighter test run (fewer steps, shorter equilibration).",
        "Try running on a machine with more GPU VRAM, or reduce precision/memory footprint if applicable.",
        "Check for unusually large solvent boxes or unexpected ligands/waters in the input.",
      ],
    };
  }

  if (blob.includes("disk") || blob.includes("no space") || blob.includes("filesystem") || blob.includes("enospc")) {
    return {
      title: "Disk or storage issue",
      likelyCauses: ["Not enough disk space for outputs/checkpoints.", "Volume mount or permissions issue on the server."],
      fixes: [
        "Free disk space on the data volume and retry.",
        "Verify the service data directory is mounted and writable by the worker.",
        "Reduce trajectory/checkpoint frequency if outputs are very large.",
      ],
    };
  }

  if (blob.includes("pdbfixer") || blob.includes("missing residue") || blob.includes("missing atoms")) {
    return {
      title: "Structure/parameterization problem (PDBFixer/OpenMM prep)",
      likelyCauses: [
        "Missing residues or atoms in the input structure.",
        "Unusual nonstandard residues not handled automatically.",
      ],
      fixes: [
        "Inspect the input PDB/mmCIF in a viewer and fix missing atoms/residues before upload.",
        "Try enabling/disabling “replace nonstandard residues” options if available in prep settings.",
        "Remove nonessential crystallization artifacts (salts, solvents) unless needed.",
      ],
    };
  }

  if (blob.includes("forcefield") || blob.includes("atom type") || blob.includes("openff") || blob.includes("parameter")) {
    return {
      title: "Force field / parameterization problem",
      likelyCauses: [
        "Ligand chemistry not covered by the available force fields.",
        "Undefined stereochemistry or unsupported atom types.",
      ],
      fixes: [
        "Check ligand protonation, charges, and stereochemistry (prefer SDF/MOL2 with explicit bonds).",
        "Simplify the ligand or try a different tautomer/protonation state.",
        "Review parameterization logs in the Logs tab for the exact offending residue/atom.",
      ],
    };
  }

  if (blob.includes("timeout") || blob.includes("timed out") || blob.includes("deadline")) {
    return {
      title: "Timeout or stalled step",
      likelyCauses: ["A stage took longer than expected or the worker lost heartbeat."],
      fixes: [
        "Retry the job; if it repeats, check server/worker health and GPU availability.",
        "Consider smaller steps or fewer stages for a first test run.",
      ],
    };
  }

  if (blob.includes("cancel")) {
    return {
      title: "Run canceled",
      likelyCauses: ["You or an administrator stopped the job."],
      fixes: ["Use Retry to start again, or adjust inputs/settings before retrying."],
    };
  }

  if (blob.includes("permission") || blob.includes("forbidden") || blob.includes("access denied")) {
    return {
      title: "Permission / access issue",
      likelyCauses: ["File permissions or ownership problems on the server data volume."],
      fixes: [
        "Verify the service is running with the expected user/group and data directories are writable.",
        "Contact your administrator if this is a shared deployment.",
      ],
    };
  }

  // Generic fallback if there is any error code/message
  if (c === "simulate_failed" || c === "stage_failed" || c === "prep_failed" || c === "prep_worker_error") {
    return {
      title: "Run failed during simulation/prep",
      likelyCauses: ["The worker reported a failure in the current step."],
      fixes: [
        "Open the Logs tab and read the last ERROR/Traceback from the relevant log.",
        "Try a smaller test input to isolate data vs. resource issues.",
        "If the error mentions a file or residue, fix the input and retry.",
      ],
    };
  }

  if (code || message) {
    return {
      title: "Run failed",
      likelyCauses: ["The simulation or preparation step reported an error."],
      fixes: [
        "Open the Logs tab and search for the first ERROR/Traceback near the end of the relevant log.",
        "Try a smaller test input to isolate whether the issue is data- or resource-related.",
        "If the message mentions a specific file/residue, fix the input structure and retry.",
      ],
    };
  }

  return null;
}
