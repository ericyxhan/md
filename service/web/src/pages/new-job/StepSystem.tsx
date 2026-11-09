import { Droplets, FlaskConical, Info, ShieldCheck } from "lucide-react";
import type { Capabilities } from "../../lib/types";
import {
  Field,
  SuffixInput,
  TextInput,
  Toggle,
} from "../../components/ui/Form";
import type { Draft } from "./draft";

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
          <div className="flex items-end">
            <p className="flex items-start gap-1.5 text-[11.5px] leading-relaxed text-muted">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              Solvent molecules and ions are added automatically. The worker
              enforces the server&apos;s upload and step limits.
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
