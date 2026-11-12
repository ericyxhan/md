import { Plus, Trash2 } from "lucide-react";
import type { ChainInfo, FileInspect } from "../../lib/types";
import { formatCompact } from "../../lib/utils";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";

type SelectionPanelProps = {
  inspect: FileInspect;
  onAddEdit: (
    operation: "select_chain" | "remove_ligand",
    label: string,
    step: { chain_to_keep?: string; ligand_to_remove?: string },
  ) => void;
};

/**
 * Renders the structure inspection data as interactive chips.
 * Clicking a chain adds a "keep chain" edit; clicking a ligand adds a
 * "remove ligand" edit. Both map onto the existing /prep/system-prep
 * operations (zero API change).
 */
export function SelectionPanel({
  inspect,
  onAddEdit,
}: SelectionPanelProps) {
  const chains = Object.entries(inspect.chains).sort(([a], [b]) =>
    a.localeCompare(b),
  );

  return (
    <div className="space-y-4">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-faint">
          Chains
        </p>
        <div className="flex flex-wrap gap-2 mt-2">
          {chains.map(([chainId, info]) => (
            <ChainChip
              key={chainId}
              chainId={chainId}
              info={info}
              onAddEdit={onAddEdit}
            />
          ))}
        </div>
      </div>

      {inspect.ligands.length > 0 ? (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-faint">
            Ligands
          </p>
          <div className="flex flex-wrap gap-2 mt-2">
            {inspect.ligands.map((ligand) => (
              <LigandChip
                key={ligand}
                ligand={ligand}
                onAddEdit={onAddEdit}
              />
            ))}
          </div>
        </div>
      ) : null}

      <div className="pt-3 border-t border-line">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-faint">
          Composition
        </p>
        <div className="grid grid-cols-2 gap-2 mt-2 text-[11px]">
          <CompositionRow label="Protein" value={inspect.components.protein} tone="brand" />
          <CompositionRow label="Water" value={inspect.components.water} tone="brand" />
          <CompositionRow label="Ions" value={inspect.components.ion} tone="brand" />
          <CompositionRow label="Ligands" value={inspect.components.ligand} tone="brand" />
          <CompositionRow label="Total atoms" value={inspect.atom_count} tone="ink" />
          <CompositionRow label="Models" value={inspect.model_count} tone="ink" />
        </div>
      </div>
    </div>
  );
}

function ChainChip({
  chainId,
  info,
  onAddEdit,
}: {
  chainId: string;
  info: ChainInfo;
  onAddEdit: SelectionPanelProps["onAddEdit"];
}) {
  return (
    <button
      type="button"
      onClick={() =>
        onAddEdit(
          "select_chain",
          `Keep chain ${chainId}`,
          { chain_to_keep: chainId },
        )
      }
      className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-[11.5px] font-medium text-ink transition hover:bg-brand-50 hover:border-brand-300"
    >
      <span className="text-brand-600">{chainId}</span>
      <span className="text-muted">{formatCompact(info.residue_count)} residues</span>
      <Plus className="size-3 text-brand-600" />
    </button>
  );
}

function LigandChip({
  ligand,
  onAddEdit,
}: {
  ligand: string;
  onAddEdit: SelectionPanelProps["onAddEdit"];
}) {
  return (
    <button
      type="button"
      onClick={() =>
        onAddEdit(
          "remove_ligand",
          `Remove ligand ${ligand}`,
          { ligand_to_remove: ligand },
        )
      }
      className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-[11.5px] font-medium text-ink transition hover:bg-rose-50 hover:border-rose-300"
    >
      <span className="text-rose-600">{ligand}</span>
      <Trash2 className="size-3 text-rose-600" />
    </button>
  );
}

function CompositionRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "brand" | "ink";
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-muted">{label}</span>
      <span
        className={cn(
          "text-ink-soft font-mono tabular-nums",
          tone === "brand" && "text-brand-700",
        )}
      >
        {formatCompact(value)}
      </span>
    </div>
  );
}