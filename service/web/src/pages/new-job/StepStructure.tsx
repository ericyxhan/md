import { Suspense } from "react";
import {
  Boxes,
  Dna,
  Globe2,
  Info,
  Plus,
  Trash2,
} from "lucide-react";
import type { Capabilities, FileOut, SystemPrepStep } from "../../lib/types";
import { filePreviewUrl } from "../../lib/api";
import { formatBytes, structureFormat, titleCase } from "../../lib/utils";
import { FileDropzone } from "../../components/upload/FileDropzone";
import {
  Field,
  SegmentedControl,
  TextInput,
} from "../../components/ui/Form";
import type { Draft } from "./draft";
import { StructurePreview } from "../../components/viewer/StructurePreview";
import { SelectionPanel } from "../../components/viewer/SelectionPanel";
import { EditStack } from "../../components/viewer/EditStack";
import { Card, CardBody } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { AlertCircle } from "lucide-react";
import { useFileInspect } from "../../lib/queries";

type UploadedStructurePreviewProps = {
  file: FileOut;
  header: string;
};

function UploadedStructurePreview({
  file,
  header,
}: UploadedStructurePreviewProps) {
  const format = structureFormat(file.name);
  const previewable = Boolean(format);

  return (
    <Card className="overflow-hidden">
      <CardBody className="px-5 py-5 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-[12px] font-semibold text-ink">{header}</p>
          {previewable ? (
            <p className="text-[11px] text-muted">
              {formatBytes(file.size_bytes)}
            </p>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-0.5 text-[11px] text-muted">
              <AlertCircle className="mt-0.5 size-3.5" />
              Not renderable
            </span>
          )}
        </div>

        {previewable ? (
          <StructurePreview
            url={filePreviewUrl(file.id)}
            format={format ?? undefined}
            label={file.name}
            sourceSizeBytes={file.size_bytes}
            className="h-[260px] overflow-hidden rounded-lg border border-line bg-surface relative"
          />
        ) : (
          <EmptyState
            icon={<AlertCircle className="size-5 text-amber-600" />}
            title="Preview unavailable"
            description={`
              ${file.name} ({formatBytes(file.size_bytes)}) is supported for
              upload but does not have a viewer representation yet. Use the
              download button in Artifacts after launch to inspect it locally.
            `.trim()}
          />
        )}
      </CardBody>
    </Card>
  );
}

type StructureEditorProps = {
  file: FileOut;
  onAddEdit: (
    operation: "select_chain" | "remove_ligand",
    label: string,
    step: { chain_to_keep?: string; ligand_to_remove?: string },
  ) => void;
  edits: SystemPrepStep[];
  onRemoveEdit: (id: string) => void;
  onClearEdits: () => void;
};

function StructureEditor({
  file,
  onAddEdit,
  edits,
  onRemoveEdit,
  onClearEdits,
}: StructureEditorProps) {
  const inspect = useFileInspect(file.id);

  if (inspect.isLoading) {
    return (
      <Card className="overflow-hidden">
        <CardBody className="px-5 py-8">
          <div className="flex flex-col items-center justify-center text-center">
            <p className="text-[12.5px] text-muted">Inspecting structure…</p>
          </div>
        </CardBody>
      </Card>
    );
  }

  if (inspect.isError) {
    return (
      <Card className="overflow-hidden">
        <CardBody className="px-5 py-8">
          <EmptyState
            icon={<AlertCircle className="size-5 text-rose-600" />}
            title="Could not inspect structure"
            description={
              inspect.error instanceof Error
                ? inspect.error.message
                : "The structure could not be analyzed."
            }
          />
        </CardBody>
      </Card>
    );
  }

  if (!inspect.data) {
    return null;
  }

  return (
    <div className="space-y-4">
      <SelectionPanel
        inspect={inspect.data}
        onAddEdit={onAddEdit}
      />
      <EditStack
        entries={edits.map((edit, index) => ({
          id: String(index),
          operation: edit.operation,
          label:
            edit.operation === "select_chain"
              ? `Keep chain ${edit.chain_to_keep}`
              : edit.operation === "remove_ligand"
                ? `Remove ligand ${edit.ligand_to_remove}`
                : edit.operation,
          residue_specs: [],
        }))}
        onRemove={onRemoveEdit}
        onClear={onClearEdits}
      />
    </div>
  );
}

export function StepStructure({
  draft,
  onChange,
  capabilities,
}: {
  draft: Draft;
  onChange: (next: Draft) => void;
  capabilities: Capabilities;
}) {
  const maxBytes = capabilities.limits.max_upload_bytes;
  const allFormats = capabilities.input_formats.all;
  const proteinFormats = capabilities.input_formats.protein;
  const ligandFormats = capabilities.input_formats.ligand;

  const addLigand = (file: FileOut) => {
    onChange({ ...draft, ligandFiles: [...draft.ligandFiles, file] });
  };
  const removeLigand = (id: string) => {
    onChange({
      ...draft,
      ligandFiles: draft.ligandFiles.filter((file) => file.id !== id),
    });
  };

  const addEdit = (
    operation: "select_chain" | "remove_ligand",
    label: string,
    step: { chain_to_keep?: string; ligand_to_remove?: string },
  ) => {
    onChange({
      ...draft,
      prepEdits: [...draft.prepEdits, { operation, ...step }],
    });
  };

  const removeEdit = (id: string) => {
    onChange({
      ...draft,
      prepEdits: draft.prepEdits.filter((_, index) => String(index) !== id),
    });
  };

  const clearEdits = () => {
    onChange({ ...draft, prepEdits: [] });
  };

  const hasStructure = Boolean(draft.complexFile ?? draft.proteinFile);
  const hasEdits = draft.prepEdits.length > 0;

  return (
    <div className="space-y-6">
      <Field
        label="Simulation name"
        hint="A short label you will recognise later. You can change it by creating a new run."
        htmlFor="job-name"
      >
        <TextInput
          id="job-name"
          className="input-lg"
          placeholder="e.g. 7YAE · kinase inhibitor replicate 1"
          maxLength={capabilities.limits.max_name_length}
          value={draft.name}
          onChange={(event) =>
            onChange({ ...draft, name: event.target.value })
          }
          autoFocus
        />
      </Field>

      <div>
        <p className="field-label">What are you simulating?</p>
        <SegmentedControl
          value={draft.inputMode}
          onChange={(inputMode) =>
            onChange({ ...draft, inputMode, prepEdits: [], prepOutputFileId: null })
          }
          options={[
            { value: "complex", label: "Complex file" },
            { value: "protein_ligands", label: "Protein + ligands" },
            {
              value: "pdb_id",
              label: "PDB ID",
              disabled: !capabilities.pdb_download_enabled,
            },
          ]}
        />
        <p className="field-hint">
          {draft.inputMode === "complex"
            ? "One file that already contains the protein and every ligand."
            : draft.inputMode === "protein_ligands"
              ? "Upload the receptor separately from one or more ligand files."
              : capabilities.pdb_download_enabled
                ? "Download a public structure from RCSB by its four-character ID."
                : "PDB download is disabled on this server."}
        </p>
      </div>

      {draft.inputMode === "complex" ? (
        <>
          <FileDropzone
            file={draft.complexFile}
            accept={allFormats}
            maxBytes={maxBytes}
            title="Drop the protein–ligand complex here"
            hint="PDB, mmCIF, SDF, MOL, or MOL2"
            onUploaded={(file) =>
              onChange({ ...draft, complexFile: file, prepEdits: [], prepOutputFileId: null })
            }
            onRemove={() =>
              onChange({ ...draft, complexFile: null, prepEdits: [], prepOutputFileId: null })
            }
          />
          {draft.complexFile ? (
            <>
              <UploadedStructurePreview
                file={draft.complexFile}
                header="Preview"
              />
              <StructureEditor
                file={draft.complexFile}
                onAddEdit={addEdit}
                edits={draft.prepEdits}
                onRemoveEdit={removeEdit}
                onClearEdits={clearEdits}
              />
              {hasEdits && (
                <p className="text-[11px] text-muted">
                  Edits will be applied by preparing the structure before the
                  simulation runs.
                </p>
              )}
              <MembraneHint />
            </>
          ) : null}

        </>
      ) : null}

      {draft.inputMode === "protein_ligands" ? (
        <div className="space-y-5">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Dna className="size-4 text-brand-600" />
              <p className="text-[13px] font-semibold text-ink">
                Protein structure
              </p>
            </div>
            <FileDropzone
              file={draft.proteinFile}
              accept={proteinFormats}
              maxBytes={maxBytes}
              title="Drop the protein file here"
              hint="PDB, mmCIF"
              onUploaded={(file) =>
                onChange({
                  ...draft,
                  proteinFile: file,
                  prepEdits: [],
                  prepOutputFileId: null,
                })
              }
              onRemove={() =>
                onChange({
                  ...draft,
                  proteinFile: null,
                  prepEdits: [],
                  prepOutputFileId: null,
                })
              }
            />
            {draft.proteinFile ? (
              <>
                <UploadedStructurePreview
                  file={draft.proteinFile}
                  header="Preview"
                />
                <StructureEditor
                  file={draft.proteinFile}
                  onAddEdit={addEdit}
                  edits={draft.prepEdits}
                  onRemoveEdit={removeEdit}
                  onClearEdits={clearEdits}
                />
                {hasEdits && (
                  <p className="text-[11px] text-muted">
                    Edits will be applied by preparing the structure before the
                    simulation runs.
                  </p>
                )}
                <MembraneHint />
              </>
            ) : null}
          </div>

          <div>
            <div className="mb-2 flex items-center gap-2">
              <Boxes className="size-4 text-brand-600" />
              <p className="text-[13px] font-semibold text-ink">
                Ligands
                {draft.ligandFiles.length > 0 ? (
                  <span className="ml-1.5 font-normal text-muted">
                    {draft.ligandFiles.length} uploaded
                  </span>
                ) : null}
              </p>
            </div>

            {draft.ligandFiles.length > 0 ? (
              <ul className="mb-3 divide-y divide-line rounded-xl border border-line bg-surface">
                {draft.ligandFiles.map((file) => (
                  <li
                    key={file.id}
                    className="flex items-center gap-3 px-3.5 py-2.5"
                  >
                    <span className="flex size-7 items-center justify-center rounded-md bg-brand-50 text-brand-700">
                      <Boxes className="size-3.5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12.5px] font-medium text-ink">
                        {file.name}
                      </p>
                      <p className="text-[10.5px] text-faint">
                        {formatBytes(file.size_bytes)} ·{" "}
                        {titleCase(file.content_type.split("/").pop() ?? "file")}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeLigand(file.id)}
                      className="rounded-md p-1.5 text-faint transition hover:bg-rose-50 hover:text-rose-600"
                      aria-label={`Remove ${file.name}`}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            <FileDropzone
              accept={ligandFormats}
              maxBytes={maxBytes}
              title={
                draft.ligandFiles.length
                  ? "Add another ligand"
                  : "Drop ligand files here"
              }
              hint={`Up to ${capabilities.limits.max_ligands} ligands · ${ligandFormats.join(", ")}`}
              onUploaded={addLigand}
            />
            {draft.ligandFiles.length > 0 ? (
              <p className="mt-2 flex items-center gap-1.5 text-[11px] text-muted">
                <Plus className="size-3" />
                Files are matched to residues during preparation.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {draft.inputMode === "pdb_id" ? (
        <div>
          <Field
            label="RCSB PDB ID"
            hint="A four-character accession, for example 7YAE."
            htmlFor="pdb-id"
          >
            <div className="relative">
              <Globe2 className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
              <TextInput
                id="pdb-id"
                className="input-lg pl-9 font-mono uppercase tracking-[0.18em]"
                placeholder="7YAE"
                maxLength={4}
                disabled={!capabilities.pdb_download_enabled}
                value={draft.pdbId}
                onChange={(event) =>
                  onChange({
                    ...draft,
                    pdbId: event.target.value
                      .replace(/[^0-9a-zA-Z]/g, "")
                      .slice(0, 4),
                  })
                }
              />
            </div>
          </Field>
        </div>
      ) : null}
    </div>
  );
}

function MembraneHint() {
  return (
    <div className="space-y-4 rounded-xl border border-brand-200/70 bg-brand-50/50 p-3.5">
      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-white text-brand-700 shadow-sm ring-1 ring-inset ring-brand-200/60">
        <Info className="size-3.5" />
      </span>
      <div className="text-[12.5px] leading-relaxed text-ink-soft">
        <p className="font-medium text-ink">Working with a membrane protein?</p>
        <p className="mt-0.5 text-muted">
          If you want a lipid bilayer in your simulation, use membrane embedding
          first. Build your complete complex here, then embed it in a membrane
          before creating the simulation. Simulating a bare membrane protein
          directly will not include a bilayer.
        </p>
      </div>
    </div>
  );
}
