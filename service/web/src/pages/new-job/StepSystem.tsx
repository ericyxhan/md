import { useEffect, useState } from "react";
import { Droplets, FlaskConical, Info, ShieldCheck } from "lucide-react";
import type { Capabilities } from "../../lib/types";
import {
  Field,
  Select,
  SuffixInput,
  TextInput,
  Toggle,
} from "../../components/ui/Form";
import type { Draft } from "./draft";

function parseResidueNames(text: string): string[] {
  return Array.from(
    new Set(
      text
        .split(/[,\s]+/)
        .map((name) => name.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
}

/**
 * Keep free-form editing local until blur so typing a comma does not rewrite
 * the input on every keystroke. The draft stores the parsed list.
 */
function ResidueNamesInput({
  value,
  onChange,
}: {
  value: string[];
  onChange: (names: string[]) => void;
}) {
  const [text, setText] = useState(value.join(", "));

  useEffect(() => {
    setText(value.join(", "));
  }, [value]);

  return (
    <TextInput
      id="strip-residues"
      value={text}
      placeholder="SO4, GOL, EDO"
      onChange={(event) => setText(event.target.value)}
      onBlur={() => onChange(parseResidueNames(text))}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        }
      }}
    />
  );
}

export function StepSystem({
  draft,
  onChange,
  capabilities,
}: {
  draft: Draft;
  onChange: (next: Draft) => void;
  capabilities: Capabilities;
}) {
  const parameterization = draft.parameterization;
  const patch = (values: Partial<typeof parameterization>) =>
    onChange({
      ...draft,
      parameterization: { ...parameterization, ...values },
    });

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-xl border border-brand-200/70 bg-brand-50/50 p-3.5">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-white text-brand-700 shadow-sm ring-1 ring-inset ring-brand-200/60">
          <FlaskConical className="size-3.5" />
        </span>
        <div className="text-[12.5px] leading-relaxed text-ink-soft">
          <p className="font-medium text-ink">Parameterization is automatic</p>
          <p className="mt-0.5 text-muted">
            We protonate the system, add missing atoms, build a solvent box, and
            assign force fields. Proteins use{" "}
            <span className="font-medium text-ink-soft">
              {capabilities.fixed_forcefields.join(" + ")}
            </span>
            ; ligands use{" "}
            <span className="font-medium text-ink-soft">
              {capabilities.ligand_forcefield}
            </span>
            .
          </p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Field
          label="pH"
          hint="Protonation state for titratable residues."
          htmlFor="ph"
        >
          <TextInput
            id="ph"
            type="number"
            min={0}
            max={14}
            step={0.1}
            value={parameterization.ph}
            onChange={(event) =>
              patch({ ph: Number(event.target.value) })
            }
          />
        </Field>

        <Field
          label="Box shape"
          hint="Periodic box shape. Non-cubic shapes reduce water for the same padding."
          htmlFor="box-shape"
        >
          <select
            id="box-shape"
            value={parameterization.box_shape ?? "cube"}
            onChange={(event) => patch({ box_shape: event.target.value })}
            className="w-full rounded-md border border-line px-3 py-2 text-sm"
          >
            <option value="cube">Cube</option>
            <option value="dodecahedron">Dodecahedron</option>
            <option value="octahedron">Truncated octahedron</option>
          </select>
        </Field>

        <Field
          label="Solvent padding"
          hint="Buffer distance around the solute."
          htmlFor="padding"
        >
          <SuffixInput
            id="padding"
            type="number"
            min={0.5}
            max={2}
            step={0.1}
            suffix="nm"
            value={parameterization.padding_nm}
            onChange={(event) =>
              patch({ padding_nm: Number(event.target.value) })
            }
          />
        </Field>

        <Field
          label="Ionic strength"
          hint="Salt concentration, with counter-ions."
          htmlFor="ionic"
        >
          <SuffixInput
            id="ionic"
            type="number"
            min={0}
            max={1}
            step={0.05}
            suffix="M"
            value={parameterization.ionic_strength_molar}
            onChange={(event) =>
              patch({ ionic_strength_molar: Number(event.target.value) })
            }
          />
        </Field>
      </div>

      <div className="space-y-4 rounded-xl border border-line bg-surface-muted/50 p-4">
        <Toggle
          checked={parameterization.add_missing_residues}
          onChange={(checked) => patch({ add_missing_residues: checked })}
          label="Add missing residues"
          description="Rebuild loops or side chains absent from the uploaded structure. Leave this off if the structure is complete or you want to preserve gaps."
        />
        <div className="h-px bg-line" />
        <Toggle
          checked={parameterization.allow_undefined_stereo}
          onChange={(checked) => patch({ allow_undefined_stereo: checked })}
          label="Allow undefined stereochemistry"
          description="Permit ligands whose stereocenters are not specified. Useful for exploratory work; off by default to avoid physically ambiguous systems."
        />
        <div className="h-px bg-line" />
        <Toggle
          checked={parameterization.strip_crystallographic_waters}
          onChange={(checked) =>
            patch({ strip_crystallographic_waters: checked })
          }
          label="Remove crystallographic waters"
          description={
            parameterization.strip_crystallographic_waters
              ? "Input waters will be removed before the new solvent box is built."
              : "Input waters are kept and new solvent is added around them. Enable to remove them before solvation."
          }
        />
      </div>

      <details className="group rounded-xl border border-line bg-surface">
        <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-[13px] font-medium text-ink-soft">
          Advanced preparation limits
          <span className="text-[11px] font-normal text-faint group-open:hidden">
            Show
          </span>
          <span className="hidden text-[11px] font-normal text-faint group-open:inline">
            Hide
          </span>
        </summary>
        <div className="grid gap-4 border-t border-line px-4 py-4 sm:grid-cols-2">
          <Field
            label="Maximum ligand residues"
            hint="Reject ligands larger than this."
            htmlFor="max-ligand-residues"
          >
            <TextInput
              id="max-ligand-residues"
              type="number"
              min={0}
              max={100}
              value={parameterization.max_ligand_residues}
              onChange={(event) =>
                patch({ max_ligand_residues: Number(event.target.value) })
              }
            />
          </Field>
          <Field
            label="Residues to remove"
            hint="Names such as SO4, GOL, or NA; case-insensitive. Leave empty to keep them."
            htmlFor="strip-residues"
          >
            <ResidueNamesInput
              value={parameterization.strip_residues}
              onChange={(names) => patch({ strip_residues: names })}
            />
          </Field>
          <div className="space-y-3 sm:col-span-2">
            <Toggle
              checked={parameterization.strip_existing_hydrogens}
              onChange={(checked) =>
                patch({ strip_existing_hydrogens: checked })
              }
              label="Rebuild input hydrogens"
              description="Remove hydrogens from protein/complex inputs and rebuild them from the residue templates and pH. Turn this off only for a structure with a deliberate custom protonation state."
            />
            <div className="h-px bg-line" />
            <Toggle
              checked={parameterization.replace_nonstandard_residues}
              onChange={(checked) =>
                patch({ replace_nonstandard_residues: checked })
              }
              label="Replace modified residues"
              description="Map MSE, SEP, TPO, and similar modifications back to standard residues in long, mostly-standard chains. D-peptide and nonstandard-rich chains are left intact."
            />
          </div>
          <Field
            label="Positive ion"
            hint="Ion used to neutralize the solvent box."
            htmlFor="positive-ion"
          >
            <Select
              id="positive-ion"
              value={parameterization.positive_ion}
              onChange={(event) =>
                patch({ positive_ion: event.target.value })
              }
            >
              {["Na+", "K+", "Li+", "Cs+", "Rb+"].map((ion) => (
                <option key={ion} value={ion}>
                  {ion}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Negative ion"
            hint="Counter-ion used to neutralize the solvent box."
            htmlFor="negative-ion"
          >
            <Select
              id="negative-ion"
              value={parameterization.negative_ion}
              onChange={(event) =>
                patch({ negative_ion: event.target.value })
              }
            >
              {["Cl-", "Br-", "F-", "I-"].map((ion) => (
                <option key={ion} value={ion}>
                  {ion}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Solvent model"
            hint="Water model passed to the solvent builder."
            htmlFor="solvent-model"
          >
            <Select
              id="solvent-model"
              value={parameterization.solvent_model}
              onChange={(event) =>
                patch({ solvent_model: event.target.value })
              }
            >
              {["tip3p", "spce", "tip4pew", "tip5p", "swm4ndp"].map(
                (model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ),
              )}
            </Select>
          </Field>
          <Field
            label="Biomolecule support"
            hint="Force-field modules included in the prepared system."
            htmlFor="biomolecule-types"
          >
            <div className="flex flex-wrap gap-3 pt-1">
              {(["dna", "rna", "glycan", "lipid"] as const).map((type) => {
                const checked =
                  parameterization.biomolecule_types.includes(type);
                return (
                  <label
                    key={type}
                    className="inline-flex items-center gap-2 text-[12px] text-ink-soft"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const next = event.target.checked
                          ? [...parameterization.biomolecule_types, type]
                          : parameterization.biomolecule_types.filter(
                              (item) => item !== type,
                            );
                        patch({
                          biomolecule_types: next.includes("protein")
                            ? next
                            : ["protein", ...next],
                        });
                      }}
                    />
                    {type.toUpperCase()}
                  </label>
                );
              })}
            </div>
          </Field>
          <div className="flex items-end sm:col-span-2">
            <p className="flex items-start gap-1.5 text-[11.5px] leading-relaxed text-muted">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              New solvent molecules and ions are added automatically. Input
              waters are kept unless removed above. The worker enforces the
              server&apos;s upload and step limits.
            </p>
          </div>
        </div>
      </details>

      <div className="flex items-center gap-2 text-[11.5px] text-muted">
        <ShieldCheck className="size-3.5 text-brand-600" />
        Fixed force fields keep runs reproducible and comparable.
        <span className="ml-auto inline-flex items-center gap-1 text-faint">
          <Droplets className="size-3" />
          TIP3P water
        </span>
      </div>
    </div>
  );
}
