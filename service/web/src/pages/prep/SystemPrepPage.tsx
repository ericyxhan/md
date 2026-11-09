import {
  useCallback,
  useState,
  type ChangeEvent,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Download,
  FileUp,
  Globe2,
  Loader2,
  Minus,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";
import type {
  FileOut,
  PDBInspection,
  SystemPrepOut,
  SystemPrepRequest,
  SystemPrepStep,
} from "../../lib/types";
import {
  cancelPrepJob,
  getPrepJob,
  listPrepJobs,
  requestSystemPrep,
} from "../../lib/api";
import { usePrepJob, usePrepJobs, useCapabilities } from "../../lib/queries";
import { useToast } from "../../components/ui/Toast";
import { PageHeader } from "../../components/layout/PageHeader";
import { Button } from "../../components/ui/Button";
import { Card, CardBody } from "../../components/ui/Card";
import { EmptyState, PageLoader } from "../../components/ui/EmptyState";
import { FileDropzone } from "../../components/upload/FileDropzone";
import { Field, Select, SuffixInput, Toggle } from "../../components/ui/Form";
import { ProgressBar } from "../../components/ui/Progress";
import { cn } from "../../lib/utils";

const OPERATIONS: Array<{
  value: SystemPrepStep["operation"];
  label: string;
  description: string;
}> = [
  {
    value: "remove_ligand",
    label: "Remove ligand",
    description: "Strip all residues with a given name from the structure",
  },
  {
    value: "select_chain",
    label: "Keep chain",
    description: "Keep only one chain and discard the rest",
  },
  {
    value: "add_ligand",
    label: "Add ligand",
    description: "Append a ligand molecule (SDF/MOL/PDB) to the structure",
  },
];

export default function SystemPrepPage() {
  const { prepJobId } = useParams<{ prepJobId?: string }>();
  const navigate = useNavigate();
  const { push } = useToast();
  const queryClient = useQueryClient();

  // ========================================================================
  // Viewing an existing prep job
  // ========================================================================

  if (prepJobId) {
    const { data: prepJob, isLoading: isLoadingJob, refetch } = usePrepJob(
      prepJobId
    );

    if (isLoadingJob) return <PageLoader label="Loading preparation job" />;
    if (!prepJob) {
      return (
        <div className="mx-auto w-full max-w-[700px] px-4 py-6 sm:px-6 lg:px-8">
          <EmptyState
            icon={<AlertCircle className="size-6" />}
            title="Preparation job not found"
            description="That prep job does not exist or you do not have access to it."
            action={
              <Button onClick={() => navigate("/prep/system-prep")}>
                Create a new preparation
              </Button>
            }
          />
        </div>
      );
    }

    const terminal =
      prepJob.status === "completed" ||
      prepJob.status === "failed" ||
      prepJob.status === "canceled";
    const active = prepJob.status === "queued" || prepJob.status === "running";
    const canDownload =
      prepJob.status === "completed" && prepJob.output_file_ids.length > 0;

    return (
      <div className="mx-auto w-full max-w-[700px] px-4 py-6 sm:px-6 lg:px-8">
        <PageHeader
          title="System preparation"
          description={
            prepJob.status === "completed"
              ? "Preparation complete"
              : prepJob.status === "failed"
                ? "Preparation failed"
                : prepJob.status === "canceled"
                  ? "Preparation canceled"
                  : `Preparing ${prepJob.status}…`
          }
        />

        <Card className="mb-6">
          <CardBody className="p-6">
            <div className="space-y-5">
              <div className="flex items-start justify-between gap-2">
                <span className="text-[13px] text-ink-soft">Status</span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
                    prepJob.status === "completed"
                      ? "bg-emerald-50 text-emerald-700"
                      : prepJob.status === "failed"
                        ? "bg-rose-50 text-rose-700"
                        : prepJob.status === "canceled"
                          ? "bg-amber-50 text-amber-700"
                          : "bg-brand-50 text-brand-700",
                  )}
                >
                  {prepJob.status.charAt(0).toUpperCase() +
                    prepJob.status.slice(1)}
                </span>
              </div>

              {prepJob.phase && (
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[13px] text-ink-soft">Phase</span>
                  <span className="text-[13px] font-medium text-ink">
                    {prepJob.phase.charAt(0).toUpperCase() +
                      prepJob.phase.slice(1)}
                  </span>
                </div>
              )}

              {active && prepJob.progress_percent != null && (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[13px] text-ink-soft">Progress</span>
                    <span className="text-[13px] font-medium text-ink">
                      {prepJob.progress_percent}%{" "}
                      {prepJob.progress_percent === 100 ? "(finalizing…)" : ""}
                    </span>
                  </div>
                  <ProgressBar
                    value={prepJob.progress_percent ?? 0}
                    className="h-3"
                  />
                </div>
              )}

              {prepJob.error && (
                <div className="rounded-md p-3 bg-rose-50 border border-rose-100">
                  <p className="text-[12.5px] text-rose-700">
                    {prepJob.error}
                  </p>
                </div>
              )}

              {canDownload && (
                <div className="space-y-2">
                  <p className="text-[12.5px] font-semibold text-ink">
                    Output files
                  </p>
                  <div className="space-y-1.5">
                    {prepJob.output_file_ids.map((fileId, index) => (
                      <div
                        key={fileId}
                        className="flex items-center gap-3 px-3 py-2 rounded-lg border border-line bg-surface"
                      >
                        <span className="flex size-8 items-center justify-center rounded-md bg-brand-50 text-brand-700">
                          {index === 0 ? <FileUp className="size-3.5" /> : <RotateCcw className="size-3.5" />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[12.5px] font-medium text-ink">
                            Prepared structure (PDB)
                          </p>
                          <p className="text-[11px] text-faint">
                            Download to use outside Lattice
                          </p>
                        </div>
                        <a
                          href={`/api/v1/files/${fileId}`}
                          className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
                          title="Download"
                        >
                          <Download className="size-4" />
                        </a>
                        <button
                          type="button"
                          onClick={() => {
                            navigate(`/new?prepFileId=${fileId}`);
                          }}
                          className="rounded-md p-1.5 text-brand-700 transition hover:bg-brand-50 hover:text-brand-800"
                          title="Use in simulation"
                        >
                          <Globe2 className="size-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <Button
                    variant="primary"
                    onClick={() =>
                      navigate(`/new?prepFileId=${prepJob.output_file_ids[0]}`)
                    }
                    className="w-full"
                    disabled={!prepJob.output_file_ids[0]}
                  >
                    Use prepared system in simulation
                  </Button>
                </div>
              )}

              {active && !terminal && (
                <div className="space-y-2">
                  <Button
                    variant="danger"
                    onClick={async () => {
                      if (
                        !window.confirm(
                          "Cancel this preparation? This cannot be undone."
                        )
                      )
                        return;
                      try {
                        const res = await cancelPrepJob(prepJobId);
                        if (res.status === "canceled") {
                          push({
                            title: "Cancellation requested",
                            description:
                              "The preparation will be canceled as soon as possible.",
                            tone: "info",
                          });
                          queryClient.invalidateQueries({ queryKey: ["prep"] });
                          refetch();
                        }
                      } catch (cause) {
                        push({
                          title: "Cancel failed",
                          description:
                            cause instanceof Error
                              ? cause.message
                              : "Could not cancel the preparation",
                          tone: "error",
                        });
                      }
                    }}
                    className="w-full sm:w-auto"
                  >
                    Cancel preparation
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => refetch()}
                    className="w-full sm:w-auto"
                  >
                    <RefreshCw className="size-4" /> Refresh
                  </Button>
                </div>
              )}

              {!active && !terminal && (
                <div className="flex items-center gap-2 text-[12.5px] text-muted">
                  <Loader2 className="size-4" />
                  Waiting for a prep worker to pick up this job…
                </div>
              )}

              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  onClick={() => navigate("/prep/system-prep")}
                >
                  New preparation
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  // ========================================================================
  // Creating a new prep job
  // ========================================================================

  const [inputFile, setInputFile] = useState<FileOut | null>(null);
  const [pdbId, setPdbId] = useState("");
  const [steps, setSteps] = useState<SystemPrepStep[]>([
    { operation: "remove_ligand", ligand_to_remove: undefined },
  ]);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(
    null
  );

  const { data: capabilities, refetch: refetchCapabilities } =
    useCapabilities();

  const prepEnabled = !!capabilities; // system prep doesn't need packmol

  const prepMutation = useMutation({
    mutationFn: requestSystemPrep,
    onSuccess: (data: SystemPrepOut) => {
      queryClient.invalidateQueries({ queryKey: ["prep"] });
      navigate(`/prep/system-prep/${data.prep_job_id}`);
    },
    onError: (cause: unknown) => {
      const message =
        cause instanceof Error ? cause.message : "Preparation request failed";
      push({ title: "Preparation failed", description: message, tone: "error" });
    },
  });

  const isPrepping = prepMutation.isPending;

  const inputSelected = !!inputFile || pdbId.length === 4;
  const canSubmit =
    inputSelected &&
    steps.length > 0 &&
    !isPrepping &&
    prepEnabled;

  const handleSubmit = (event: ChangeEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;

    const payload: SystemPrepRequest = {
      name: `System preparation · ${new Date().toLocaleString()}`,
      input_file_id: inputFile?.id ?? null,
      pdb_id: pdbId.length === 4 ? pdbId.toUpperCase() : null,
      steps: steps.map((step) => ({
        operation: step.operation,
        ligand_to_remove:
          step.operation === "remove_ligand"
            ? step.ligand_to_remove?.trim().toUpperCase() || undefined
            : undefined,
        chain_to_keep:
          step.operation === "select_chain"
            ? step.chain_to_keep?.trim().toUpperCase() || undefined
            : undefined,
        ligand_file_ids:
          step.operation === "add_ligand"
            ? (step.ligand_file_ids ?? []).filter(Boolean)
            : undefined,
      })),
    };

    prepMutation.mutate(payload);
  };

  const addStep = (operation: SystemPrepStep["operation"]) => {
    setSteps((prev) => [
      ...prev,
      { operation, ligand_to_remove: undefined, chain_to_keep: undefined, ligand_file_ids: [] },
    ]);
  };

  const removeStep = (index: number) => {
    setSteps((prev) => prev.filter((_, i) => i !== index));
  };

  const updateStep = (index: number, field: keyof SystemPrepStep, value: any) => {
    setSteps((prev) =>
      prev.map((step, i) =>
        i === index ? { ...step, [field]: value } : step
      )
    );
  };

  const addLigandFile = (stepIndex: number, fileId: string) => {
    setSteps((prev) =>
      prev.map((step, i) => {
        if (i !== stepIndex) return step;
        return {
          ...step,
          ligand_file_ids: step.ligand_file_ids
            ? [...step.ligand_file_ids, fileId]
            : [fileId],
        };
      })
    );
  };

  const removeLigandFile = (stepIndex: number, fileIdToRemove: string) => {
    setSteps((prev) =>
      prev.map((step, i) => {
        if (i !== stepIndex) return step;
        return {
          ...step,
          ligand_file_ids: (step.ligand_file_ids ?? []).filter(
            (id) => id !== fileIdToRemove
          ),
        };
      })
    );
  };

  const { data: prepJobs } = usePrepJobs();

  return (
    <div className="mx-auto w-full max-w-[700px] px-4 py-6 sm:px-6 lg:px-8">
      <PageHeader
        title="System preparation"
        description="Remove ligands, select chains, or add ligands to prepare a structure for MD simulation"
      />

      {!capabilities && (
        <div className="mb-6">
          <PageLoader label="Checking system preparation availability" />
        </div>
      )}

      {capabilities && (
        <form onSubmit={handleSubmit} className="space-y-6">
          <Card>
            <CardBody className="p-6">
              <div className="space-y-5">
                <div>
                  <p className="text-[13px] font-semibold text-ink mb-2">
                    1. Input structure
                  </p>
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          setInputFile(null);
                          setPdbId("");
                        }}
                        className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
                        title="Upload a file"
                      >
                        <FileUp className="size-4" />
                      </button>
                      <FileDropzone
                        file={inputFile}
                        accept={[".pdb", ".cif", ".mmcif"]}
                        maxBytes={50 * 1024 * 1024}
                        title="Upload a protein structure"
                        hint="PDB, CIF, or mmCIF structure to prepare"
                        onUploaded={setInputFile}
                        onRemove={() => setInputFile(null)}
                        disabled={isPrepping}
                      />
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          setInputFile(null);
                        }}
                        className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
                        title="Use a PDB ID"
                      >
                        <Globe2 className="size-4" />
                      </button>
                      <Field
                        label="PDB ID"
                        htmlFor="system-prep-pdb-id"
                        hint="Download a structure from RCSB by PDB ID"
                      >
                        <input
                          id="system-prep-pdb-id"
                          type="text"
                          maxLength={4}
                          value={pdbId}
                          onChange={(event) =>
                            setPdbId(event.target.value.toUpperCase())
                          }
                          disabled={isPrepping || !!inputFile}
                          className="w-full text-uppercase"
                          placeholder="7YAE"
                        />
                      </Field>
                    </div>
                  </div>
                </div>

                <div>
                  <p className="text-[13px] font-semibold text-ink mb-2">
                    2. Preparation steps
                  </p>
                  <p className="text-[12.5px] text-muted">
                    Steps run in order. Each step transforms the output of the previous step.
                  </p>
                  <div className="space-y-3">
                    {steps.map((step, index) => {
                      const op = OPERATIONS.find((o) => o.value === step.operation);
                      return (
                        <Card
                          key={index}
                          className="border-line p-4 sm:p-5"
                        >
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                                Step {index + 1}
                              </span>
                              <span className="text-[12px] font-medium text-ink">
                                {op?.label}
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={() => removeStep(index)}
                              className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
                              title="Remove step"
                            >
                              <Minus className="size-4" />
                            </button>
                          </div>

                          <Field
                            label="Operation"
                            hint="What to do in this step"
                          >
                            <Select
                              value={step.operation}
                              onChange={(event) => {
                                const val = event.target.value as SystemPrepStep["operation"];
                                updateStep(index, "operation", val);
                              }}
                              disabled={isPrepping}
                            >
                              {OPERATIONS.map((item) => (
                                <option key={item.value} value={item.value}>
                                  {item.label}
                                </option>
                              ))}
                            </Select>
                          </Field>

                          {step.operation === "remove_ligand" && (
                            <Field
                              label="Ligand residue name"
                              htmlFor={`remove-ligand-${index}`}
                              hint="Three-letter residue code, e.g. CLR"
                            >
                              <input
                                id={`remove-ligand-${index}`}
                                type="text"
                                maxLength={5}
                                value={step.ligand_to_remove ?? ""}
                                onChange={(event) =>
                                  updateStep(
                                    index,
                                    "ligand_to_remove",
                                    event.target.value
                                  )
                                }
                                disabled={isPrepping}
                                className="text-uppercase w-full"
                                placeholder="CLR"
                              />
                            </Field>
                          )}

                          {step.operation === "select_chain" && (
                            <Field
                              label="Chain ID to keep"
                              htmlFor={`select-chain-${index}`}
                              hint="Single-character chain ID, e.g. A"
                            >
                              <input
                                id={`select-chain-${index}`}
                                type="text"
                                maxLength={2}
                                value={step.chain_to_keep ?? ""}
                                onChange={(event) =>
                                  updateStep(index, "chain_to_keep", event.target.value)
                                }
                                disabled={isPrepping}
                                className="text-uppercase w-full"
                                placeholder="A"
                              />
                            </Field>
                          )}

                          {step.operation === "add_ligand" && (
                            <div className="space-y-3">
                              <Field
                                label="Ligand files"
                                htmlFor={`add-ligand-${index}`}
                                hint="SDF, MOL, or PDB ligand files to add"
                              >
                                <FileDropzone
                                  file={null}
                                  accept={[".sdf", ".mol", ".pdb", ".mol2"]}
                                  maxBytes={50 * 1024 * 1024}
                                  title="Upload ligand(s)"
                                  hint="Select SDF/MOL/PDB ligand files"
                                  onUploaded={(file) =>
                                    addLigandFile(index, file.id)
                                  }
                                  disabled={isPrepping}
                                />
                                {(step.ligand_file_ids ?? []).length > 0 && (
                                  <div className="space-y-1 mt-3">
                                    {(step.ligand_file_ids ?? []).map(
                                      (fileId, fileIndex) => (
                                      <div
                                        key={fileId}
                                        className="flex items-center gap-2 px-2 py-1 rounded-md border border-line bg-surface"
                                      >
                                        <span className="text-[11px] text-muted">
                                          Ligand {fileIndex + 1}
                                        </span>
                                        <button
                                          type="button"
                                          onClick={() =>
                                            removeLigandFile(index, fileId)
                                          }
                                          className="rounded-md p-1 text-faint transition hover:bg-ink/5 hover:text-ink"
                                        >
                                          <Trash2 className="size-3.5" />
                                        </button>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </Field>
                            </div>
                          )}
                        </Card>
                      );
                    })}
                  </div>
                  <div className="flex gap-2">
                    {OPERATIONS.map((op) => (
                      <button
                        key={op.value}
                        type="button"
                        onClick={() => addStep(op.value)}
                        disabled={isPrepping || steps.length >= 10}
                        className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink transition hover:bg-brand-50 hover:text-brand-900"
                      >
                        <Plus className="size-4" /> {op.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="pt-4 flex justify-end">
                <Button
                  type="submit"
                  variant="primary"
                  disabled={!canSubmit}
                  loading={isPrepping}
                  className="w-full sm:w-auto"
                >
                  {isPrepping ? "Preparing…" : "Start preparation"}
                </Button>
              </div>
            </CardBody>
          </Card>
          {prepJobs && prepJobs.length > 0 && (
            <Card>
              <CardBody className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-[13px] font-semibold text-ink">
                    Recent preparations
                  </h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => queryClient.invalidateQueries({ queryKey: ["prep"] })}
                  >
                    Refresh
                  </Button>
                </div>
                <div className="space-y-2">
                  {prepJobs.slice(0, 5).map((job) => (
                    <div
                      key={job.id}
                      className="flex items-center justify-between px-3 py-2.5 rounded-lg border border-line bg-surface/50"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-[12.5px] font-medium text-ink truncate">
                          System preparation · {job.type}
                        </p>
                        <p className="text-[11px] text-faint">
                          {job.status} ·
                          {new Date(job.created_at).toLocaleString()}
                        </p>
                      </div>
                      <span
                        className={cn(
                          "text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-md",
                          job.status === "completed"
                            ? "bg-emerald-50 text-emerald-700"
                            : job.status === "failed"
                              ? "bg-rose-50 text-rose-700"
                              : job.status === "canceled"
                                ? "bg-amber-50 text-amber-700"
                                : "bg-brand-50 text-brand-700",
                        )}
                      >
                        {job.status}
                      </span>
                      <button
                        type="button"
                        onClick={() => navigate(`/prep/system-prep/${job.id}`)}
                        className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
                        title="View details"
                      >
                        <Globe2 className="size-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}
        </form>
      )}
    </div>
  );
}
