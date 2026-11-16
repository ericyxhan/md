import { useEffect, useState, type ChangeEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Download,
  Plus,
  Target,
} from "lucide-react";
import type { DockingOut, FileOut } from "../../lib/types";
import {
  cancelPrepJob,
  getFile,
  getPrepJob,
  requestDocking,
} from "../../lib/api";
import { usePrepJob, usePrepJobs, useCapabilities } from "../../lib/queries";
import { useToast } from "../../components/ui/Toast";
import { PageHeader } from "../../components/layout/PageHeader";
import { Button } from "../../components/ui/Button";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { EmptyState, PageLoader } from "../../components/ui/EmptyState";
import { FileDropzone } from "../../components/upload/FileDropzone";
import { Field } from "../../components/ui/Form";
import { ProgressBar } from "../../components/ui/Progress";
import { cn, isPrepActive } from "../../lib/utils";
import { PrepJobRow } from "../../components/jobs/PrepJobCards";

export default function DockingPage() {
  const { prepJobId } = useParams<{ prepJobId?: string }>();
  if (prepJobId) return <DockingJobView prepJobId={prepJobId} />;
  return <DockingForm />;
}

function DockingForm() {
  const navigate = useNavigate();
  const { push } = useToast();
  const queryClient = useQueryClient();
  const [receptorFile, setReceptorFile] = useState<FileOut | null>(null);
  const [ligandFile, setLigandFile] = useState<FileOut | null>(null);
  const [ligandSmiles, setLigandSmiles] = useState("");
  const [exhaustiveness, setExhaustiveness] = useState(8);
  const [numPoses, setNumPoses] = useState(9);
  const [formOpen, setFormOpen] = useState(true);

  const { data: capabilities } = useCapabilities();
  const { data: prepJobs } = usePrepJobs();
  const dockings = (prepJobs ?? []).filter((j) => j.type === "docking");
  const dockingEnabled = capabilities?.prep_workflows?.docking?.enabled ?? false;

  const [searchParams] = useSearchParams();
  const prepFileId = searchParams.get("prepFileId");
  useEffect(() => {
    if (!prepFileId || receptorFile) return;
    getFile(prepFileId)
      .then(setReceptorFile)
      .catch(() => {});
  }, [prepFileId, receptorFile]);

  const mutation = useMutation({
    mutationFn: requestDocking,
    onSuccess: (data: DockingOut) => {
      queryClient.invalidateQueries({ queryKey: ["prep"] });
      navigate(`/prep/docking/${data.prep_job_id}`);
    },
    onError: (cause: unknown) => {
      push({
        title: "Docking failed",
        description: cause instanceof Error ? cause.message : "Docking request failed",
        tone: "error",
      });
    },
  });

  const canSubmit =
    !!receptorFile &&
    (!!ligandFile || ligandSmiles.trim().length > 0) &&
    !mutation.isPending &&
    dockingEnabled;

  const handleSubmit = (e: ChangeEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!receptorFile || !canSubmit) return;
    mutation.mutate({
      receptor_file_id: receptorFile.id,
      ligand_file_ids: ligandFile ? [ligandFile.id] : [],
      ligand_smiles: ligandSmiles.trim() ? [ligandSmiles.trim()] : [],
      box_center: null,
      box_size: null,
      exhaustiveness,
      num_poses: numPoses,
      seed: null,
    });
  };

  if (capabilities && !dockingEnabled) {
    return (
      <div className="mx-auto max-w-[760px]">
        <PageHeader title="Docking" description="Predict binding poses for a ligand in a receptor" />
        <EmptyState
          icon={<AlertCircle className="size-6" />}
          title="Docking unavailable"
          description="Docking requires Vina/Meeko on the prep worker. Contact your administrator to enable DOCKING_ENABLED."
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Docking"
        description="Predict binding poses for a ligand in a receptor"
        actions={
          <Button variant="primary" leadingIcon={<Plus className="size-4" />} onClick={() => setFormOpen(true)}>
            New docking
          </Button>
        }
      />

      {formOpen && (
        <form onSubmit={handleSubmit} className="space-y-6">
          <Card className="max-w-[760px]">
            <CardBody className="p-6 space-y-5">
              <Field label="Receptor">
                <FileDropzone
                  accept={[".pdb", ".cif", ".mmcif"]}
                  onUploaded={setReceptorFile}
                  file={receptorFile}
                  maxBytes={50 * 1024 * 1024}
                />
              </Field>
              <Field label="Ligand file (optional if SMILES provided)">
                <FileDropzone
                  accept={[".sdf", ".mol", ".mol2", ".pdb", ".cif", ".mmcif"]}
                  onUploaded={setLigandFile}
                  file={ligandFile}
                  maxBytes={50 * 1024 * 1024}
                />
              </Field>
              <Field label="Or ligand SMILES">
                <input
                  type="text"
                  value={ligandSmiles}
                  onChange={(e) => setLigandSmiles(e.target.value)}
                  className="w-full rounded-md border border-line px-3 py-2 text-sm"
                  placeholder="CC(=O)Oc1ccccc1C(=O)O"
                />
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Exhaustiveness">
                  <input
                    type="number"
                    value={exhaustiveness}
                    onChange={(e) => setExhaustiveness(Number(e.target.value))}
                    min={1}
                    max={64}
                    className="w-full rounded-md border border-line px-3 py-2 text-sm"
                  />
                </Field>
                <Field label="Number of poses">
                  <input
                    type="number"
                    value={numPoses}
                    onChange={(e) => setNumPoses(Number(e.target.value))}
                    min={1}
                    max={20}
                    className="w-full rounded-md border border-line px-3 py-2 text-sm"
                  />
                </Field>
              </div>
              <Button type="submit" variant="primary" disabled={!canSubmit} loading={mutation.isPending}>
                Run docking
              </Button>
            </CardBody>
          </Card>
        </form>
      )}

      <Card className={formOpen ? "mt-6" : ""}>
        <CardHeader
          title="All docking runs"
          description="Every docking job in this workspace, newest first."
          action={
            <Button variant="ghost" size="sm" onClick={() => queryClient.invalidateQueries({ queryKey: ["prep"] })}>
              Refresh
            </Button>
          }
        />
        {dockings.length === 0 ? (
          <EmptyState
            icon={<Target className="size-5" />}
            title="No docking runs yet"
            description="Dock a ligand into a receptor, then use the top pose to launch simulations."
            action={
              <Button variant="primary" leadingIcon={<Plus className="size-4" />} onClick={() => setFormOpen(true)}>
                New docking
              </Button>
            }
          />
        ) : (
          <div className="divide-y divide-line">
            {dockings.map((job) => (
              <PrepJobRow key={job.id} job={job} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function DockingJobView({ prepJobId }: { prepJobId: string }) {
  const navigate = useNavigate();
  const { push } = useToast();
  const { data: prepJob, isLoading } = usePrepJob(prepJobId);
  if (isLoading) return <PageLoader label="Loading docking job" />;
  if (!prepJob) {
    return (
      <div className="mx-auto max-w-[760px]">
        <EmptyState
          icon={<AlertCircle className="size-6" />}
          title="Docking job not found"
          description="That job does not exist or you do not have access."
          action={<Button onClick={() => navigate("/prep/docking")}>New docking</Button>}
        />
      </div>
    );
  }
  const active = isPrepActive(prepJob.status);
  const canDownload = prepJob.status === "completed" && prepJob.output_file_ids.length > 0;
  return (
    <div>
      <PageHeader
        title="Docking"
        description={
          prepJob.status === "completed"
            ? "Docking complete"
            : prepJob.status === "failed"
              ? "Docking failed"
              : prepJob.status === "canceled"
                ? "Docking canceled"
                : `Docking ${prepJob.status}…`
        }
      />
      <Card className="mb-6 max-w-[760px]">
        <CardBody className="p-6 space-y-4">
          <div className="flex justify-between text-sm">
            <span className="text-ink-soft">Status</span>
            <span className="font-medium text-ink">{prepJob.status}</span>
          </div>
          {prepJob.phase && (
            <div className="flex justify-between text-sm">
              <span className="text-ink-soft">Phase</span>
              <span className="font-medium text-ink">{prepJob.phase}</span>
            </div>
          )}
          {active && (
            <div className="space-y-2">
              <ProgressBar value={prepJob.progress_percent ?? 100} className="h-3" animated={prepJob.progress_percent == null} />
              {prepJob.progress_message && (
                <p className="text-[11.5px] text-muted">{prepJob.progress_message}</p>
              )}
            </div>
          )}
          {prepJob.error && (
            <div className="rounded-md p-3 bg-rose-50 border border-rose-100">
              <p className="text-[12.5px] text-rose-700">{prepJob.error}</p>
            </div>
          )}
          {canDownload && (
            <div className="space-y-2">
              <p className="text-[12.5px] font-semibold text-ink">Output files</p>
              {prepJob.output_file_ids.map((fileId, index) => (
                <div key={fileId} className="flex items-center gap-3 px-3 py-2 rounded-lg border border-line bg-surface">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12.5px] font-medium text-ink">
                      {index === 0 ? "Docked complex (PDB)" : index === 1 ? "Poses (PDBQT)" : "Scores (CSV)"}
                    </p>
                  </div>
                  <a href={`/api/v1/files/${fileId}`} className="rounded-md p-1.5 text-faint hover:text-ink" title="Download">
                    <Download className="size-4" />
                  </a>
                  {index === 0 && (
                    <button
                      type="button"
                      onClick={() => navigate(`/new?prepFileId=${fileId}`)}
                      className="rounded-md p-1.5 text-brand-700 hover:text-brand-800"
                      title="Use in simulation"
                    >
                      <Target className="size-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
