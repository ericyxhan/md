import { Suspense, useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Download,
  FileUp,
  Globe2,
  Layers,
  Loader2,
  Minus,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";
import type {
  FileInspect,
  FileOut,
  SystemPrepOut,
  SystemPrepRequest,
  SystemPrepStep,
} from "../../lib/types";
import {
  cancelPrepJob,
  createWorkflow,
  fetchPdb,
  filePreviewUrl,
  getPrepJob,
  listPrepJobs,
  requestSystemPrep,
} from "../../lib/api";
import {
  useCapabilities,
  usePrepJob,
  usePrepJobs,
  useFileInspect,
} from "../../lib/queries";
import { useToast } from "../../components/ui/Toast";
import { PageHeader } from "../../components/layout/PageHeader";
import { Button } from "../../components/ui/Button";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { EmptyState, PageLoader, Spinner } from "../../components/ui/EmptyState";
import { FileDropzone } from "../../components/upload/FileDropzone";
import { PrepJobRow } from "../../components/jobs/PrepJobCards";
import { Field } from "../../components/ui/Form";
import { ProgressBar } from "../../components/ui/Progress";
import { cn, formatCompact, isPrepActive } from "../../lib/utils";
import { structureFormat } from "../../lib/utils";
import { StructurePreview } from "../../components/viewer/StructurePreview";
import { SelectionPanel } from "../../components/viewer/SelectionPanel";
import { EditStack } from "../../components/viewer/EditStack";

type StructurePreviewCardProps = {
  url: string;
  file: FileOut;
  inspect: FileInspect | null;
  isLoading: boolean;
}

function StructurePreviewCard({
  url,
  file,
  inspect,
  isLoading,
}: StructurePreviewCardProps) {
  const format = structureFormat(file.name);
  const previewable = Boolean(format);

  if (isLoading) {
    return (
      <Card className="overflow-hidden">
        <CardBody className="px-5 py-8">
          <div className="flex flex-col items-center justify-center text-center">
            <Spinner className="size-4" />
            <p className="mt-2 text-[12.5px] text-muted">Inspecting structure\u2026</p>
          </div>
        </CardBody>
      </Card>
    );
  }

  if (!previewable) {
    return (
      <Card className="overflow-hidden">
        <CardBody className="px-5 py-8">
          <EmptyState
            icon={<AlertCircle className="size-5 text-amber-600" />}
            title="Preview unavailable"
            description={file.name + " (" + formatCompact(file.size_bytes) + ") is supported for upload but does not have a viewer representation yet."}
          />
        </CardBody>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <CardBody className="px-5 py-4 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-[12px] font-semibold text-ink">Structure preview</p>
          <p className="text-[11px] text-muted">{formatCompact(file.size_bytes)}</p>
        </div>

        <StructurePreview
          url={url}
          format={format ?? undefined}
          label={file.name}
          sourceSizeBytes={file.size_bytes}
          className="h-[320px] overflow-hidden rounded-lg border border-line bg-surface relative"
        />

        {inspect && (
          <div className="grid grid-cols-2 gap-4 text-[11px]">
            <MetricRow label="Total atoms" value={formatCompact(inspect.atom_count)} tone="ink" />
            <MetricRow label="Models" value={inspect.model_count} tone="ink" />
            <MetricRow label="Protein" value={formatCompact(inspect.components.protein)} tone="brand" />
            <MetricRow label="Water" value={formatCompact(inspect.components.water)} tone="brand" />
            <MetricRow label="Ions" value={formatCompact(inspect.components.ion)} tone="brand" />
            <MetricRow label="Ligands" value={formatCompact(inspect.components.ligand)} tone="brand" />
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function MetricRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: "brand" | "ink";
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-muted">{label}</span>
      <span className={cn("text-ink-soft font-mono tabular-nums", tone === "brand" && "text-brand-700")}>
        {value}
      </span>
    </div>
  );
}

export default function SystemPrepPage() {
  const { prepJobId } = useParams<{ prepJobId?: string }>();

  // The view and the form are separate components on purpose.  Handling
  // both in one component with an early return changes the number of hooks
  // React sees between renders, which violates the Rules of Hooks: React
  // throws "Rendered more hooks than during the previous render" and, with
  // no error boundary above it, the whole page goes blank until a refresh.
  if (prepJobId) {
    return <SystemPrepJobView prepJobId={prepJobId} />;
  }
  return <SystemPrepForm />;
}

/**
 * Shows a claimed or finished system-preparation job.
 */
function SystemPrepJobView({ prepJobId }: { prepJobId: string }) {
  const navigate = useNavigate();
  const { push } = useToast();
  const queryClient = useQueryClient();

  const createWorkflowMutation = useMutation({
    mutationFn: (payload: { name: string; source_file_id: string; source_type: string }) =>
      createWorkflow(payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      push({
        title: "Workflow created",
        description:
          "'" +
          data.name +
          "' is now a base system. Launch variant simulations from the Workflows page.",
        tone: "info",
      });
      navigate("/workflows/" + data.id);
    },
    onError: (cause: unknown) => {
      push({
        title: "Workflow creation failed",
        description:
          cause instanceof Error ? cause.message : "Could not create the workflow.",
        tone: "error",
      });
    },
  });

  {
    const { data: prepJob, isLoading: isLoadingJob, refetch } = usePrepJob(prepJobId);

    // Hoisted above the early returns: a hook that is only reached after a
    // conditional return would change the hook count between the loading
    // and the loaded render, which React rejects.
    const outputFileId = prepJob?.output_file_ids[0];
    const canDownload =
      prepJob?.status === "completed" &&
      (prepJob.output_file_ids?.length ?? 0) > 0;
    const outputInspect = useFileInspect(outputFileId, canDownload);

    if (isLoadingJob) return <PageLoader label="Loading preparation job" />;
    if (!prepJob) {
      return (
        <div>
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
    const active = isPrepActive(prepJob.status);

    return (
      <div>
        <PageHeader
          className="max-w-[760px]"
          title="System preparation"
          description={
            prepJob.status === "completed"
              ? "Preparation complete"
              : prepJob.status === "failed"
                ? "Preparation failed"
                : prepJob.status === "canceled"
                  ? "Preparation canceled"
                  : "Preparing " + prepJob.status + "\u2026"
          }
        />

        <Card className="mb-6 max-w-[760px]">
          <CardBody className="p-6">
            <div className="space-y-5">
              <div className="flex items-start justify-between gap-2">
                <span className="text-[13px] text-ink-soft">Status</span>
                <span className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
                  prepJob.status === "completed"
                    ? "bg-emerald-50 text-emerald-700"
                    : prepJob.status === "failed"
                      ? "bg-rose-50 text-rose-700"
                        : prepJob.status === "canceled"
                          ? "bg-amber-50 text-amber-700"
                          : "bg-brand-50 text-brand-700",
                )}>
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

              {active && (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[13px] text-ink-soft">Progress</span>
                    <span className="text-[13px] font-medium text-ink">
                      {prepJob.progress_percent != null
                        ? `${Math.round(prepJob.progress_percent)}%`
                        : "Working…"}
                    </span>
                  </div>
                  <ProgressBar
                    value={prepJob.progress_percent ?? 100}
                    className="h-3"
                    animated={prepJob.progress_percent == null}
                  />
                  {prepJob.progress_message ? (
                    <p className="text-[11.5px] leading-relaxed text-muted">
                      {prepJob.progress_message}
                    </p>
                  ) : null}
                </div>
              )}

              {prepJob.error && (
                <div className="rounded-md p-3 bg-rose-50 border border-rose-100">
                  <p className="text-[12.5px] text-rose-700">{prepJob.error}</p>
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
                          href={"/api/v1/files/" + fileId}
                          className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
                          title="Download"
                        >
                          <Download className="size-4" />
                        </a>
                        <button
                          type="button"
                          onClick={() => {
                            navigate("/new?prepFileId=" + fileId);
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
                      navigate("/new?prepFileId=" + prepJob.output_file_ids[0])
                    }
                    className="w-full"
                    disabled={!prepJob.output_file_ids[0]}
                  >
                    Use prepared system in simulation
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() =>
                      navigate(
                        "/prep/membrane?prepFileId=" +
                          prepJob.output_file_ids[0]
                      )
                    }
                    className="w-full sm:w-auto mt-2"
                    disabled={!prepJob.output_file_ids[0]}
                  >
                    Use in membrane embedding
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      createWorkflowMutation.mutate({
                        name:
                          "Workflow · " +
                          prepJob.type +
                          " · " +
                          new Date().toLocaleDateString(),
                        source_file_id: prepJob.output_file_ids[0]!,
                        source_type: "system_prep",
                      });
                    }}
                    className="w-full sm:w-auto mt-2"
                    disabled={
                      !prepJob.output_file_ids[0] ||
                      createWorkflowMutation.isPending
                    }
                  >
                    {createWorkflowMutation.isPending ? "Creating…" : "Save as workflow base system"}
                  </Button>
                </div>
              )}

              {canDownload && prepJob.output_file_ids.length > 0 && (
                <Card className="mb-6 max-w-[760px] overflow-hidden">
                  <CardHeader
                    title="Output structure"
                    description="Solute-focused view of the prepared system"
                  />
                  <CardBody className="px-5 py-4">
                    <StructurePreviewCard
                      url={filePreviewUrl(outputFileId ?? "")}
                      file={{
                        id: prepJob.output_file_ids[0],
                        name: "prepared.pdb",
                        size_bytes: 0,
                        sha256: "",
                        content_type: "chemical/x-pdb",
                        created_at: "",
                      }}
                      inspect={outputInspect.data ?? null}
                      isLoading={outputInspect.isLoading}
                    />
                  </CardBody>
                </Card>
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
                  Waiting for a prep worker to pick up this job\u2026
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
}

/**
 * The system-preparation request form.
 */
function SystemPrepForm() {
  const navigate = useNavigate();
  const { push } = useToast();
  const queryClient = useQueryClient();

  const [inputFile, setInputFile] = useState<FileOut | null>(null);
  const [pdbId, setPdbId] = useState("");
  const [prepEdits, setPrepEdits] = useState<SystemPrepStep[]>([]);

  // The history is the page's main content; the request form opens on demand.
  const [formOpen, setFormOpen] = useState(false);

  const { data: capabilities } = useCapabilities();

  const prepEnabled = !!capabilities;

  const prepMutation = useMutation({
    mutationFn: requestSystemPrep,
    onSuccess: (data: SystemPrepOut) => {
      queryClient.invalidateQueries({ queryKey: ["prep"] });
      navigate("/prep/system-prep/" + data.prep_job_id);
    },
    onError: (cause: unknown) => {
      const message =
        cause instanceof Error ? cause.message : "Preparation request failed";
      push({ title: "Preparation failed", description: message, tone: "error" });
    },
  });

  const fetchPdbMutation = useMutation({
    mutationFn: async (pdbId: string) => fetchPdb(pdbId),
    onSuccess: (data) => {
      setPdbId("");
      setInputFile({
        id: data.file_id,
        name: pdbId.toUpperCase() + ".pdb",
        size_bytes: 0,
        sha256: "",
        content_type: "chemical/x-pdb",
        created_at: "",
      });
      setPrepEdits([]);
    },
    onError: (cause: unknown) => {
      const message =
        cause instanceof Error ? cause.message : "Failed to fetch PDB";
      push({ title: "Fetch failed", description: message, tone: "error" });
    },
  });

  const isPrepping = prepMutation.isPending;

  const inputSelected = !!inputFile || pdbId.length === 4;
  const canSubmit =
    inputSelected &&
    prepEdits.length > 0 &&
    !isPrepping &&
    prepEnabled;

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;

    const payload: SystemPrepRequest = {
      name: "System preparation \u00b7 " + new Date().toLocaleString(),
      input_file_id: inputFile?.id ?? null,
      pdb_id: pdbId.length === 4 ? pdbId.toUpperCase() : null,
      steps: prepEdits,
    };

    prepMutation.mutate(payload);
  };

  const addEdit = (
    operation: "select_chain" | "remove_ligand",
    label: string,
    step: { chain_to_keep?: string; ligand_to_remove?: string },
  ) => {
    setPrepEdits((prev) => [...prev, { operation, ...step }]);
  };

  const removeEdit = (id: string) => {
    setPrepEdits((prev) => prev.filter((_, i) => String(i) !== id));
  };

  const clearEdits = () => setPrepEdits([]);

  const addLigandFile = (stepIndex: number, fileId: string) => {
    setPrepEdits((prev) =>
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
    setPrepEdits((prev) =>
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
  const preparations = (prepJobs ?? []).filter(
    (job) => job.type === "system_prep",
  );

  const inputInspect = useFileInspect(inputFile?.id ?? undefined, !!inputFile);

  const editEntries = prepEdits.map((step, index) => ({
    id: String(index),
    operation: step.operation,
    label:
      step.operation === "select_chain"
        ? "Keep chain " + step.chain_to_keep
        : step.operation === "remove_ligand"
          ? "Remove ligand " + step.ligand_to_remove
          : step.operation === "add_ligand"
            ? "Add " + step.ligand_file_ids?.length + " ligand(s)"
            : step.operation,
    residue_specs: [],
  }));

  return (
    <div>
      <PageHeader
        title="System preparation"
        description="Select chains and ligands on the structure to prepare it for MD simulation"
        actions={
          <Button
            variant="primary"
            leadingIcon={<Plus className="size-4" />}
            onClick={() => setFormOpen(true)}
          >
            New preparation
          </Button>
        }
      />

      {!capabilities && (
        <div className="mb-6">
          <PageLoader label="Checking system preparation availability" />
        </div>
      )}

      {capabilities && (
        <>
          {formOpen && (
            <form onSubmit={handleSubmit} className="space-y-6">
          <Card className="max-w-[760px]">
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
                          setPrepEdits([]);
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
                        onRemove={() => {
                          setInputFile(null);
                          setPdbId("");
                          setPrepEdits([]);
                        }}
                        disabled={isPrepping}
                      />
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          setInputFile(null);
                          setPdbId("");
                          setPrepEdits([]);
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
                      <button
                        type="button"
                        onClick={() => {
                          if (pdbId.length === 4) {
                            fetchPdbMutation.mutate(pdbId);
                          }
                        }}
                        disabled={
                          fetchPdbMutation.isPending ||
                          pdbId.length !== 4 ||
                          isPrepping
                        }
                        className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
                        title="Fetch PDB from RCSB"
                      >
                        {fetchPdbMutation.isPending ? (
                          <Loader2 className="size-4" />
                        ) : (
                          <Plus className="size-4" />
                        )}
                      </button>
                    </div>
                  </div>

                  {inputFile && (
                    <div className="space-y-4">
                      <StructurePreviewCard
                        url={filePreviewUrl(inputFile.id)}
                        file={inputFile}
                        inspect={inputInspect.data ?? null}
                        isLoading={inputInspect.isLoading}
                      />
                      {inputInspect.data && (
                        <>
                          <SelectionPanel
                            inspect={inputInspect.data}
                            onAddEdit={addEdit}
                          />
                          <EditStack
                            entries={editEntries}
                            onRemove={removeEdit}
                            onClear={clearEdits}
                          />
                        </>
                      )}
                    </div>
                  )}
                </div>

                <div className="pt-4 flex justify-end">
                  <Button
                    type="submit"
                    variant="primary"
                    size="md"
                    disabled={!canSubmit}
                    loading={isPrepping}
                    className="w-full sm:w-auto"
                  >
                    {isPrepping ? "Preparing\u2026" : "Start preparation"}
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>
            </form>
          )}

          <Card className={formOpen ? "mt-6" : ""}>
            <CardHeader
              title="All preparations"
              description="Every structure preparation in this workspace, newest first."
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    queryClient.invalidateQueries({ queryKey: ["prep"] })}
                >
                  Refresh
                </Button>
              }
            />
            {preparations.length === 0 ? (
              <EmptyState
                icon={<Layers className="size-5" />}
                title="No preparations yet"
                description="Prepare a structure by removing ligands, keeping a chain, or adding ligands, then use the result to launch simulations."
                action={
                  <Button
                    variant="primary"
                    leadingIcon={<Plus className="size-4" />}
                    onClick={() => setFormOpen(true)}
                  >
                    New preparation
                  </Button>
                }
              />
            ) : (
              <div className="divide-y divide-line">
                {preparations.map((job) => (
                  <PrepJobRow key={job.id} job={job} />
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
