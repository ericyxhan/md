import {
  useCallback,
  useEffect,
  useState,
  type ChangeEvent,
} from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Download,
  FileUp,
  Globe2,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import type {
  FileOut,
  LipidType,
  MembraneEmbedOut,
  PrepJobStatus,
} from "../../lib/types";
import {
  cancelPrepJob,
  createWorkflow,
  fetchPdb,
  getFile,
  getPrepJob,
  listPrepJobs,
  requestMembraneEmbed,
} from "../../lib/api";
import { usePrepJob, usePrepJobs, useCapabilities } from "../../lib/queries";
import { useToast } from "../../components/ui/Toast";
import { PageHeader } from "../../components/layout/PageHeader";
import { Button } from "../../components/ui/Button";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { EmptyState, PageLoader } from "../../components/ui/EmptyState";
import { FileDropzone } from "../../components/upload/FileDropzone";
import { Field, Select, SuffixInput, Toggle } from "../../components/ui/Form";
import { ProgressBar } from "../../components/ui/Progress";
import { PrepJobRow } from "../../components/jobs/PrepJobCards";
import { cn, isPrepActive } from "../../lib/utils";

const LIPIDS: Array<{ value: LipidType; label: string }> = [
  { value: "POPC", label: "POPC (1-palmitoyl-2-oleoyl-sn-glycero-3-phosphocholine)" },
  { value: "POPE", label: "POPE (1-palmitoyl-2-oleoyl-sn-glycero-3-phosphoethanolamine)" },
  { value: "DPPC", label: "DPPC (1,2-dipalmitoyl-sn-glycero-3-phosphocholine)" },
  { value: "DLPC", label: "DLPC (1,2-dilauroyl-sn-glycero-3-phosphocholine)" },
  { value: "DSPC", label: "DSPC (1,2-distearoyl-sn-glycero-3-phosphocholine)" },
  { value: "SOPC", label: "SOPC (1-stearoyl-2-oleoyl-sn-glycero-3-phosphocholine)" },
];

const ORIENTATIONS: Array<{ value: string | null; label: string }> = [
  { value: null, label: "None (auto-orient)" },
  { value: "pm", label: "Parallel to membrane (pm)" },
  { value: "pp", label: "Perpendicular to membrane (pp)" },
];

export default function MembraneEmbedPage() {
  const { prepJobId } = useParams<{ prepJobId?: string }>();

  // The view and the form are separate components on purpose.  Handling
  // both in one component with an early return changes the number of hooks
  // React sees between renders, which violates the Rules of Hooks: React
  // throws "Rendered more hooks than during the previous render" and, with
  // no error boundary above it, the whole page goes blank until a refresh.
  if (prepJobId) {
    return <MembraneEmbedJobView prepJobId={prepJobId} />;
  }
  return <MembraneEmbedForm />;
}

/**
 * Shows a claimed or finished membrane-embedding job.
 */
function MembraneEmbedJobView({ prepJobId }: { prepJobId: string }) {
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

  const { data: prepJob, isLoading: isLoadingJob, refetch } = usePrepJob(
    prepJobId
  );

  if (isLoadingJob) return <PageLoader label="Loading preparation job" />;
  if (!prepJob) {
    return (
      <div className="mx-auto max-w-[760px]">
        <EmptyState
          icon={<AlertCircle className="size-6" />}
          title="Preparation job not found"
          description="That prep job does not exist or you do not have access to it."
          action={
            <Button onClick={() => navigate("/prep/membrane")}>
              Create a new embedding
            </Button>
          }
        />
      </div>
    );
  }

  {
    const terminal =
      prepJob.status === "completed" ||
      prepJob.status === "failed" ||
      prepJob.status === "canceled";
    const active = isPrepActive(prepJob.status);
    const canDownload =
      prepJob.status === "completed" && prepJob.output_file_ids.length > 0;

    return (
      <div>
        <PageHeader
          className="max-w-[760px]"
          title="Membrane embedding"
          description={
            prepJob.status === "completed"
              ? "Embedding complete"
              : prepJob.status === "failed"
                ? "Embedding failed"
                : prepJob.status === "canceled"
                  ? "Embedding canceled"
                  : `Embedding ${prepJob.status}…`
          }
        />

        <Card className="mb-6 max-w-[760px]">
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
                  {prepJob.status.charAt(0).toUpperCase() + prepJob.status.slice(1)}
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
                  {prepJob.progress_updated_at ? (
                    <p className="text-[10.5px] text-faint">
                      updated {prepJob.progress_updated_at}
                    </p>
                  ) : null}
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
                            {index === 0 ? "Embedded system (PDB)" : "Membrane topology (PSF)"}
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
                    onClick={() => navigate(`/new?prepFileId=${prepJob.output_file_ids[0]}`)}
                    className="w-full"
                    disabled={!prepJob.output_file_ids[0]}
                  >
                    Use embedded system in simulation
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
                        source_type: "membrane_embed",
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

              {active && !terminal && (
                <div className="space-y-2">
                  <Button
                    variant="danger"
                    onClick={async () => {
                      if (
                        !window.confirm(
                          "Cancel this embedding? This cannot be undone."
                        )
                      )
                        return;
                      try {
                        const res = await cancelPrepJob(prepJobId);
                        if (res.status === "canceled") {
                          push({
                            title: "Cancellation requested",
                            description:
                              "The embedding will be canceled as soon as possible.",
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
                              : "Could not cancel the embedding",
                          tone: "error",
                        });
                      }
                    }}
                    className="w-full sm:w-auto"
                  >
                    Cancel embedding
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
                <Button variant="ghost" onClick={() => navigate("/prep/membrane")}>
                  New embedding
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
 * The membrane-embedding request form.
 */
function MembraneEmbedForm() {
  const navigate = useNavigate();
  const { push } = useToast();
  const queryClient = useQueryClient();


  const [proteinFile, setProteinFile] = useState<FileOut | null>(null);
  const [pdbId, setPdbId] = useState("");
  const [lipid, setLipid] = useState<LipidType>("POPC");
  const [boxPadding, setBoxPadding] = useState(1.5);
  const [orientation, setOrientation] = useState<string | null>(null);
  const [ionicStrength, setIonicStrength] = useState(0.15);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(
    null
  );

  const [searchParams] = useSearchParams();
  const prepFileId = searchParams.get("prepFileId");

  // The history is the page's main content; the request form opens on demand
  // (or immediately when arriving from a deep link that carries a file).
  const [formOpen, setFormOpen] = useState(Boolean(prepFileId));

  const { data: capabilities, refetch: refetchCapabilities } =
    useCapabilities();

  const prepEnabled =
    capabilities?.prep_workflows?.membrane_embed?.enabled ?? false;

  // If arriving from a system-prep job, auto-select its output file as the
  // protein to embed. This guides users toward the correct order: build the
  // complete complex first, then embed it in a membrane.
  useEffect(() => {
    if (!prepFileId || proteinFile) return;
    const fetchFile = async () => {
      try {
        const file = await getFile(prepFileId);
        setProteinFile(file);
      } catch {
        // Ignore; the file may not exist or may not be accessible.
      }
    };
    void fetchFile();
  }, [prepFileId, proteinFile]);

  const embedMutation = useMutation({
    mutationFn: requestMembraneEmbed,
    onSuccess: (data: MembraneEmbedOut) => {
      queryClient.invalidateQueries({ queryKey: ["prep"] });
      navigate(`/prep/membrane/${data.prep_job_id}`);
    },
    onError: (cause: unknown) => {
      const message =
        cause instanceof Error ? cause.message : "Embedding request failed";
      push({ title: "Embedding failed", description: message, tone: "error" });
    },
  });

  const isEmbedding = embedMutation.isPending;

  const fetchPdbMutation = useMutation({
    mutationFn: async (pdbId: string) => fetchPdb(pdbId),
    onSuccess: (data) => {
      setPdbId("");
      setProteinFile({
        id: data.file_id,
        name: pdbId.toUpperCase() + ".pdb",
        size_bytes: 0,
        sha256: "",
        content_type: "chemical/x-pdb",
        created_at: "",
      });
    },
    onError: (cause: unknown) => {
      const message =
        cause instanceof Error ? cause.message : "Failed to fetch PDB";
      push({ title: "Fetch failed", description: message, tone: "error" });
    },
  });

  const canSubmit =
    !!proteinFile &&
    !isEmbedding &&
    prepEnabled;

  const handleSubmit = (event: ChangeEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!proteinFile || !canSubmit) return;

    embedMutation.mutate({
      protein_file_id: proteinFile.id,
      lipid,
      box_padding_nm: boxPadding,
      orientation,
      ionic_strength_molar: ionicStrength,
    });
  };

  const { data: prepJobs } = usePrepJobs();
  const embeddings = (prepJobs ?? []).filter(
    (job) => job.type === "membrane_embed",
  );

  return (
    <div>
      <PageHeader
        title="Membrane embedding"
        description="Embed a protein structure in a lipid bilayer for MD simulation"
        actions={
          <Button
            variant="primary"
            leadingIcon={<Plus className="size-4" />}
            onClick={() => setFormOpen(true)}
          >
            New embedding
          </Button>
        }
      />

      {!capabilities && (
        <div className="mb-6">
          <PageLoader label="Checking system preparation availability" />
        </div>
      )}

      {capabilities && !capabilities.prep_workflows && (
        <EmptyState
          icon={<AlertCircle className="size-6" />}
          title="System preparation unavailable"
          description={
            "Membrane embedding requires Packmol-Memgen on the server. " +
            "Contact your administrator to configure PACKMOL_PATH."
          }
          action={
            <Button variant="secondary" onClick={() => navigate("/jobs")}>
              Browse simulations
            </Button>
          }
        />
      )}

      {capabilities?.prep_workflows?.membrane_embed?.enabled === false && (
        <EmptyState
          icon={<AlertCircle className="size-6" />}
          title="System preparation unavailable"
          description={
            "Membrane embedding requires Packmol-Memgen on the server. " +
            "Contact your administrator to configure PACKMOL_PATH."
          }
          action={
            <Button variant="secondary" onClick={() => navigate("/jobs")}>
              Browse simulations
            </Button>
          }
        />
      )}

      {capabilities?.prep_workflows?.membrane_embed?.enabled && (
        <Card className="mb-6 max-w-[760px] border-line bg-brand-50/10">
          <CardBody className="p-5">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 size-5 text-brand-700" />
              <div>
                <p className="text-[13px] font-semibold text-ink">
                  Build your complex first
                </p>
                <p className="text-[12.5px] text-muted">
                  Membrane embedding sizes the box and solvation around the
                  input structure. If you plan to add ligands or edit the
                  complex afterward, do that in{" "}
                  <button
                    onClick={() => navigate("/prep/system-prep")}
                    className="text-brand-700 underline hover:text-brand-800"
                  >
                    system preparation
                  </button>
                  first, then embed the complete complex here. Embedding a lone
                  protein and adding ligands later can cause steric clashes
                  because the box is already fixed.
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {capabilities?.prep_workflows?.membrane_embed?.enabled && (
        <>
          {formOpen && (
            <form onSubmit={handleSubmit} className="space-y-6">
          <Card className="max-w-[760px]">
            <CardBody className="p-6">
              <div className="space-y-5">
                <div>
                  <p className="text-[13px] font-semibold text-ink mb-2">
                    1. Protein structure
                  </p>
                  <FileDropzone
                    file={proteinFile}
                    accept={[".pdb", ".cif", ".mmcif"]}
                    maxBytes={50 * 1024 * 1024}
                    title="Upload a protein structure"
                    hint="PDB or mmCIF. This will be embedded into the selected lipid bilayer."
                    onUploaded={setProteinFile}
                    onRemove={() => {
                      setProteinFile(null);
                      setPdbId("");
                    }}
                    disabled={isEmbedding}
                  />
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        setProteinFile(null);
                        setPdbId("");
                      }}
                      className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
                      title="Use a PDB ID"
                    >
                      <Globe2 className="size-4" />
                    </button>
                    <Field
                      label="PDB ID"
                      htmlFor="membrane-pdb-id"
                      hint="Download a structure from RCSB by PDB ID"
                    >
                      <input
                        id="membrane-pdb-id"
                        type="text"
                        maxLength={4}
                        value={pdbId}
                        onChange={(event) =>
                          setPdbId(event.target.value.toUpperCase())
                        }
                        disabled={isEmbedding || !!proteinFile}
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
                        isEmbedding
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

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Field
                    label="Lipid type"
                    htmlFor="membrane-lipid"
                    hint="The lipid species used to build the bilayer"
                  >
                    <Select
                      id="membrane-lipid"
                      value={lipid}
                      onChange={(event) =>
                        setLipid(event.target.value as LipidType)
                      }
                      disabled={isEmbedding}
                    >
                      {LIPIDS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </Select>
                  </Field>

                  <Field
                    label="Box padding (nm)"
                    htmlFor="membrane-padding"
                    hint="Distance from the protein to the membrane box edge"
                  >
                    <SuffixInput
                      id="membrane-padding"
                      type="number"
                      min="0.5"
                      max="5"
                      step="0.1"
                      value={boxPadding}
                      onChange={(event) =>
                        setBoxPadding(parseFloat(event.target.value) || 1.5)
                      }
                      disabled={isEmbedding}
                    />
                  </Field>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Field
                    label="Orientation"
                    htmlFor="membrane-orientation"
                    hint="How the protein is oriented relative to the membrane"
                  >
                    <Select
                      id="membrane-orientation"
                      value={orientation ?? ""}
                      onChange={(event) => {
                        const val = event.target.value;
                        setOrientation(val === "" ? null : val);
                      }}
                      disabled={isEmbedding}
                    >
                      {ORIENTATIONS.map((item) => (
                        <option
                          key={item.value ?? "none"}
                          value={item.value ?? ""}
                        >
                          {item.label}
                        </option>
                      ))}
                    </Select>
                  </Field>

                  <Field
                    label="Ionic strength (M)"
                    htmlFor="membrane-ionic"
                    hint="Salt concentration for the solvated system"
                  >
                    <SuffixInput
                      id="membrane-ionic"
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      value={ionicStrength}
                      onChange={(event) =>
                        setIonicStrength(parseFloat(event.target.value) || 0.15)
                      }
                      disabled={isEmbedding}
                    />
                  </Field>
                </div>

                <div className="pt-4 flex justify-end">
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={!canSubmit}
                    loading={isEmbedding}
                    className="w-full sm:w-auto"
                  >
                    {isEmbedding ? "Embedding…" : "Start membrane embedding"}
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>
            </form>
          )}

          <Card className={formOpen ? "mt-6" : ""}>
            <CardHeader
              title="All embeddings"
              description="Every membrane embedding in this workspace, newest first."
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    queryClient.invalidateQueries({ queryKey: ["prep"] })
                  }
                >
                  Refresh
                </Button>
              }
            />
            {embeddings.length === 0 ? (
              <EmptyState
                icon={<Layers className="size-5" />}
                title="No embeddings yet"
                description="Embed a protein structure in a lipid bilayer, then use the result to launch simulations."
                action={
                  <Button
                    variant="primary"
                    leadingIcon={<Plus className="size-4" />}
                    onClick={() => setFormOpen(true)}
                  >
                    New embedding
                  </Button>
                }
              />
            ) : (
              <div className="divide-y divide-line">
                {embeddings.map((job) => (
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
