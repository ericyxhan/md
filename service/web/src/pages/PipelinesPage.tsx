import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Download,
  FileUp,
  Layers,
  Loader2,
  Plus,
  Rocket,
  Shield,
  Target,
  Trash2,
} from "lucide-react";
import type { FileOut, PrepJobStatus } from "../lib/types";
import {
  getPrepJob,
  requestDocking,
  requestMembraneEmbed,
  requestSystemPrep,
} from "../lib/api";
import { usePrepJob, useCapabilities } from "../lib/queries";
import { useToast } from "../components/ui/Toast";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import { EmptyState, PageLoader } from "../components/ui/EmptyState";
import { FileDropzone } from "../components/upload/FileDropzone";
import { Field } from "../components/ui/Form";
import { ProgressBar } from "../components/ui/Progress";
import { cn } from "../lib/utils";

type NodeKind = "upload" | "system_prep" | "membrane" | "docking" | "analysis";

interface PipelineNode {
  id: string;
  kind: NodeKind;
  // minimal config
  file: FileOut | null;
  pdbId: string;
  // system prep
  steps: { operation: string; ligand_to_remove?: string }[];
  // membrane
  lipid: string;
  boxPadding: number;
  // docking
  ligandFile: FileOut | null;
  // analysis
  jobId: string;
  exhaustiveness: number;
  numPoses: number;
  // runtime
  status: "idle" | "running" | "done" | "failed";
  output: { fileId: string; name: string } | null;
  prepJobId: string | null;
  error: string | null;
}

const KIND_LABEL: Record<NodeKind, string> = {
  analysis: "Analysis",
  upload: "Upload structure",
  system_prep: "System preparation",
  membrane: "Membrane embedding",
  docking: "Docking",
};

const KIND_ICON: Record<NodeKind, typeof FileUp> = {
  analysis: Activity,
  upload: FileUp,
  system_prep: Layers,
  membrane: Shield,
  docking: Target,
};

function newNode(kind: NodeKind): PipelineNode {
  return {
    id: Math.random().toString(36).slice(2),
    kind,
    file: null,
    pdbId: "",
    steps: [{ operation: "remove_ligand", ligand_to_remove: "" }],
    lipid: "POPC",
    boxPadding: 1.5,
    ligandFile: null,
    jobId: "",
    exhaustiveness: 8,
    numPoses: 9,
    status: "idle",
    output: null,
    prepJobId: null,
    error: null,
  };
}

const STORAGE_KEY = "moldy:pipelines";

interface SavedPipeline {
  id: string;
  name: string;
  nodes: Omit<PipelineNode, "status" | "output" | "prepJobId" | "error">[];
}

export default function PipelinesPage() {
  const navigate = useNavigate();
  const { push } = useToast();
  const { data: capabilities } = useCapabilities();
  const queryClient = useQueryClient();

  const [pipelines, setPipelines] = useState<SavedPipeline[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  });
  const [activeId, setActiveId] = useState<string | null>(null);
  const [name, setName] = useState("My pipeline");
  const [nodes, setNodes] = useState<PipelineNode[]>([newNode("upload")]);
  const [running, setRunning] = useState(false);

  const save = useCallback(() => {
    const p: SavedPipeline = {
      id: activeId ?? Math.random().toString(36).slice(2),
      name,
      nodes: nodes.map(({ status, output, prepJobId, error, ...rest }) => rest),
    };
    const next = pipelines.filter((x) => x.id !== p.id).concat(p);
    setPipelines(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setActiveId(p.id);
    push({ title: "Pipeline saved", description: name, tone: "info" });
  }, [activeId, name, nodes, pipelines, push]);

  const load = (p: SavedPipeline) => {
    setActiveId(p.id);
    setName(p.name);
    setNodes(p.nodes.map((n) => ({ ...newNode(n.kind), ...n, status: "idle", output: null, prepJobId: null, error: null })));
  };

  const addNode = (kind: NodeKind) => setNodes((ns) => [...ns, newNode(kind)]);
  const removeNode = (id: string) => setNodes((ns) => ns.filter((n) => n.id !== id));
  const move = (id: string, dir: -1 | 1) =>
    setNodes((ns) => {
      const i = ns.findIndex((n) => n.id === id);
      if (i < 0) return ns;
      const j = i + dir;
      if (j < 0 || j >= ns.length) return ns;
      const copy = [...ns];
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  const update = (id: string, patch: Partial<PipelineNode>) =>
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, ...patch } : n)));

  const runPipeline = async () => {
    setRunning(true);
    // reset statuses
    setNodes((ns) => ns.map((n) => ({ ...n, status: "idle", output: null, error: null, prepJobId: null })));
    let lastFileId: string | null = null;
    let lastFileName = "";
    // iterate with fresh node array
    const current = [...nodes];
    for (let i = 0; i < current.length; i++) {
      const node = current[i];
      // mark running
      setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, status: "running" } : n)));
      try {
        if (node.kind === "upload") {
          if (!node.file) throw new Error("No file uploaded");
          lastFileId = node.file.id;
          lastFileName = node.file.name;
          setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, status: "done", output: { fileId: node.file!.id, name: node.file!.name } } : n)));
        } else if (node.kind === "system_prep") {
          if (!lastFileId) throw new Error("No input file from previous step");
          const res = await (async () => {
            const r = await requestSystemPrep({
              name: `Pipeline step ${i + 1}`,
              input_file_id: lastFileId!,
              steps: node.steps as any,
            });
            return r;
          })();
          // poll
          const prepJobId = res.prep_job_id;
          setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, prepJobId } : n)));
          await pollPrep(prepJobId, (msg) => {
            setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, ...msg } : n)));
          });
          const job = await getPrepJob(prepJobId);
          if (job.status !== "completed" || !job.output_file_ids.length) throw new Error(job.error || "system prep failed");
          lastFileId = job.output_file_ids[0];
          lastFileName = "system_prep.pdb";
          setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, status: "done", output: { fileId: lastFileId!, name: lastFileName } } : n)));
        } else if (node.kind === "membrane") {
          if (!lastFileId) throw new Error("No input file from previous step");
          const res = await requestMembraneEmbed({
            protein_file_id: lastFileId,
            lipid: node.lipid as any,
            box_padding_nm: node.boxPadding,
            orientation: null,
            ionic_strength_molar: 0.15,
          });
          const prepJobId = res.prep_job_id;
          setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, prepJobId } : n)));
          await pollPrep(prepJobId, (msg) => {
            setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, ...msg } : n)));
          });
          const job = await getPrepJob(prepJobId);
          if (job.status !== "completed" || !job.output_file_ids.length) throw new Error(job.error || "membrane embed failed");
          lastFileId = job.output_file_ids[0];
          lastFileName = "embedded.pdb";
          setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, status: "done", output: { fileId: lastFileId!, name: lastFileName } } : n)));
        } else if (node.kind === "docking") {
          if (!lastFileId) throw new Error("No receptor from previous step");
          const res = await requestDocking({
            receptor_file_id: lastFileId,
            ligand_file_ids: node.ligandFile ? [node.ligandFile.id] : [],
            ligand_smiles: [],
            box_center: null,
            box_size: null,
            exhaustiveness: node.exhaustiveness,
            num_poses: node.numPoses,
            seed: null,
          });
          const prepJobId = res.prep_job_id;
          setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, prepJobId } : n)));
          await pollPrep(prepJobId, (msg) => {
            setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, ...msg } : n)));
          });
          const job = await getPrepJob(prepJobId);
          if (job.status !== "completed" || !job.output_file_ids.length) throw new Error(job.error || "docking failed");
          lastFileId = job.output_file_ids[0];
          lastFileName = "docked_complex.pdb";
          setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, status: "done", output: { fileId: lastFileId!, name: lastFileName } } : n)));
        } else if (node.kind === "analysis") {
          if (!node.jobId) throw new Error("No job ID provided");
          setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, status: "done", output: { fileId: node.jobId, name: "analysis" } } : n)));
        }
      } catch (e: any) {
        setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, status: "failed", error: e?.message || "failed" } : n)));
        setRunning(false);
        push({ title: "Pipeline stopped", description: e?.message || "A step failed", tone: "error" });
        return;
      }
    }
    setRunning(false);
    push({ title: "Pipeline complete", description: `Final output: ${lastFileName}`, tone: "info" });
    // store final file id for "use in simulation"
    if (lastFileId) {
      sessionStorage.setItem("pipeline:lastFileId", lastFileId);
    }
  };

  const finalFileId = nodes[nodes.length - 1]?.output?.fileId;

  return (
    <div className="mx-auto max-w-[820px]">
      <PageHeader
        title="Pipelines"
        description="Chain preparation steps, then launch a simulation from the result"
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={save}>Save</Button>
            <Button variant="primary" leadingIcon={<Rocket className="size-4" />} onClick={runPipeline} disabled={running || nodes.length === 0}>
              {running ? "Running…" : "Run pipeline"}
            </Button>
          </div>
        }
      />

      {/* Saved pipelines */}
      {pipelines.length > 0 && (
        <Card className="mb-6">
          <CardBody className="p-4">
            <p className="mb-2 text-[12px] font-semibold text-ink">Saved pipelines</p>
            <div className="flex flex-wrap gap-2">
              {pipelines.map((p) => (
                <button
                  key={p.id}
                  onClick={() => load(p)}
                  className="rounded-md border border-line bg-surface px-3 py-1.5 text-[12.5px] text-ink-soft hover:bg-surface-muted"
                >
                  {p.name}
                </button>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Builder */}
      <div className="space-y-3">
        {nodes.map((node, idx) => {
          const Icon = KIND_ICON[node.kind];
          return (
            <Card key={node.id}>
              <CardBody className="p-5 space-y-4">
                <div className="flex items-center gap-3">
                  <span className="flex size-8 items-center justify-center rounded-md bg-brand-50 text-brand-700">
                    <Icon className="size-4" />
                  </span>
                  <select
                    value={node.kind}
                    onChange={(e) => update(node.id, { kind: e.target.value as NodeKind })}
                    className="rounded-md border border-line px-2 py-1 text-sm font-medium"
                    disabled={running}
                  >
                    {(Object.keys(KIND_LABEL) as NodeKind[]).map((k) => (
                      <option key={k} value={k}>{KIND_LABEL[k]}</option>
                    ))}
                  </select>
                  <span className="ml-auto text-[11px] text-faint">Step {idx + 1}</span>
                  <button onClick={() => move(node.id, -1)} className="text-faint hover:text-ink" disabled={running}><ArrowUp className="size-4" /></button>
                  <button onClick={() => move(node.id, 1)} className="text-faint hover:text-ink" disabled={running}><ArrowDown className="size-4" /></button>
                  <button onClick={() => removeNode(node.id)} className="text-faint hover:text-rose-600" disabled={running}><Trash2 className="size-4" /></button>
                </div>

                {/* Config */}
                {node.kind === "upload" && (
                  <Field label="Structure file">
                    <FileDropzone accept={[".pdb", ".cif", ".mmcif", ".sdf", ".mol", ".mol2"]} onUploaded={(f) => update(node.id, { file: f })} file={node.file} maxBytes={50 * 1024 * 1024} />
                  </Field>
                )}
                {node.kind === "system_prep" && (
                  <div className="space-y-2">
                    <p className="text-[12px] text-muted">Removes ligands from the input structure. Enter residue names to remove (comma-separated).</p>
                    <input
                      type="text"
                      value={node.steps[0]?.ligand_to_remove ?? ""}
                      onChange={(e) => update(node.id, { steps: [{ operation: "remove_ligand", ligand_to_remove: e.target.value }] })}
                      className="w-full rounded-md border border-line px-3 py-2 text-sm"
                      placeholder="CLR, HOH"
                    />
                  </div>
                )}
                {node.kind === "membrane" && (
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Lipid">
                      <select value={node.lipid} onChange={(e) => update(node.id, { lipid: e.target.value })} className="w-full rounded-md border border-line px-3 py-2 text-sm">
                        {["POPC", "POPE", "DPPC", "DLPC", "DSPC", "SOPC"].map((l) => <option key={l}>{l}</option>)}
                      </select>
                    </Field>
                    <Field label="Box padding (nm)">
                      <input type="number" value={node.boxPadding} onChange={(e) => update(node.id, { boxPadding: Number(e.target.value) })} className="w-full rounded-md border border-line px-3 py-2 text-sm" />
                    </Field>
                  </div>
                )}
                {node.kind === "docking" && (
                  <div className="space-y-2">
                    <Field label="Ligand file (optional)">
                      <FileDropzone accept={[".sdf", ".mol", ".mol2", ".pdb", ".cif", ".mmcif"]} onUploaded={(f) => update(node.id, { ligandFile: f })} file={node.ligandFile} maxBytes={50 * 1024 * 1024} />
                    </Field>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Exhaustiveness">
                        <input type="number" value={node.exhaustiveness} onChange={(e) => update(node.id, { exhaustiveness: Number(e.target.value) })} className="w-full rounded-md border border-line px-3 py-2 text-sm" />
                      </Field>
                      <Field label="Poses">
                        <input type="number" value={node.numPoses} onChange={(e) => update(node.id, { numPoses: Number(e.target.value) })} className="w-full rounded-md border border-line px-3 py-2 text-sm" />
                      </Field>
                    </div>
                  </div>
                )}

                {node.kind === "analysis" && (
                  <div className="space-y-2">
                    <p className="text-[12px] text-muted">Analyze a completed simulation job. Enter the job ID.</p>
                    <input
                      type="text"
                      value={node.jobId}
                      onChange={(e) => update(node.id, { jobId: e.target.value })}
                      className="w-full rounded-md border border-line px-3 py-2 text-sm"
                      placeholder="job id"
                      disabled={running}
                    />
                    {node.jobId && (
                      <Button variant="ghost" size="sm" onClick={() => navigate(`/jobs/${node.jobId}`)}>
                        Open job analysis
                      </Button>
                    )}
                  </div>
                )}

                {/* Status */}
                <div className="flex items-center gap-3">
                  <span className={cn("rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase", node.status === "done" ? "bg-emerald-50 text-emerald-700" : node.status === "failed" ? "bg-rose-50 text-rose-700" : node.status === "running" ? "bg-brand-50 text-brand-700" : "bg-surface-muted text-muted")}>
                    {node.status}
                  </span>
                  {node.status === "running" && <Loader2 className="size-4 animate-spin text-brand-600" />}
                  {node.error && <span className="text-[12px] text-rose-700">{node.error}</span>}
                  {node.output && (
                    <span className="text-[12px] text-ink-soft">
                      → {node.output.name}
                    </span>
                  )}
                </div>
                {node.status === "running" && node.prepJobId && (
                  <PrepProgressInline prepJobId={node.prepJobId} />
                )}
              </CardBody>
            </Card>
          );
        })}

        <div className="flex gap-2">
          {(Object.keys(KIND_LABEL) as NodeKind[]).map((k) => (
            <Button key={k} variant="secondary" size="sm" onClick={() => addNode(k)} disabled={running}>
              <Plus className="size-3.5" /> {KIND_LABEL[k]}
            </Button>
          ))}
        </div>
      </div>

      {finalFileId && !running && (
        <Card className="mt-6">
          <CardBody className="p-5 flex items-center justify-between gap-3">
            <div>
              <p className="text-[13px] font-semibold text-ink">Pipeline output ready</p>
              <p className="text-[12px] text-muted">Use the final structure to launch a simulation.</p>
            </div>
            <Button variant="primary" leadingIcon={<Rocket className="size-4" />} onClick={() => navigate(`/new?prepFileId=${finalFileId}`)}>
              Use in simulation
            </Button>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function PrepProgressInline({ prepJobId }: { prepJobId: string }) {
  const { data } = usePrepJob(prepJobId);
  if (!data) return null;
  return (
    <div className="space-y-1">
      <ProgressBar value={data.progress_percent ?? 0} className="h-2" animated={data.progress_percent == null} />
      {data.progress_message && <p className="text-[11px] text-muted">{data.progress_message}</p>}
    </div>
  );
}

// helpers
async function pollPrep(id: string, onMsg: (m: any) => void) {
  for (let i = 0; i < 300; i++) {
    const job = await getPrepJob(id);
    onMsg({ phase: job.phase, progress_percent: job.progress_percent, progress_message: job.progress_message });
    if (job.status === "completed" || job.status === "failed" || job.status === "canceled") {
      // resolve with final
      (window as any).__lastPrepJob = job;
      return job;
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error("prep job timed out");
}

