import {
  Boxes,
  Dna,
  Globe2,
  Plus,
  Trash2,
} from "lucide-react";
import type { Capabilities, FileOut } from "../../lib/types";
import { formatBytes, titleCase } from "../../lib/utils";
import { FileDropzone } from "../../components/upload/FileDropzone";
import {
  Field,
  SegmentedControl,
  TextInput,
} from "../../components/ui/Form";
import type { Draft } from "./draft";

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
          onChange={(inputMode) => onChange({ ...draft, inputMode })}
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
        <FileDropzone
          file={draft.complexFile}
          accept={allFormats}
          maxBytes={maxBytes}
          title="Drop the protein–ligand complex here"
          hint="PDB, mmCIF, SDF, MOL, or MOL2"
          onUploaded={(file) => onChange({ ...draft, complexFile: file })}
          onRemove={() => onChange({ ...draft, complexFile: null })}
        />
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
              onUploaded={(file) => onChange({ ...draft, proteinFile: file })}
              onRemove={() => onChange({ ...draft, proteinFile: null })}
            />
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
