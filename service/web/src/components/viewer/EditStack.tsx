import { Minus, Plus, Trash2 } from "lucide-react";
import type { ResidueSpec, SystemPrepOperation } from "../../lib/types";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";

type EditEntry = {
  id: string;
  operation: SystemPrepOperation;
  label: string;
  residue_specs: ResidueSpec[];
};

type EditStackProps = {
  entries: EditEntry[];
  onRemove: (id: string) => void;
  onClear: () => void;
};

/**
 * A stack of pending structure edits. Each entry mirrors a SystemPrepStep and
 * can be removed individually. The stack is submitted as a single prep job.
 */
export function EditStack({
  entries,
  onRemove,
  onClear,
}: EditStackProps) {
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <Minus className="mb-2 size-4 text-faint" />
        <p className="text-[12px] text-muted">
          No edits yet. Select chains or ligands above to build an edit stack.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between border-b border-line pb-2 mb-4">
        <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-faint">
          Edit stack
        </span>
        <Button
          variant="danger"
          size="sm"
          onClick={onClear}
          leadingIcon={<Trash2 className="size-3" />}
        >
          Clear all
        </Button>
      </div>

      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2.5"
        >
          <span
            className={cn(
              "shrink-0 rounded-md px-2 py-0.5 text-[10px] font-bold",
              entry.operation === "remove_residues" ||
              entry.operation === "remove_ligand"
                ? "bg-rose-50 text-rose-700"
                : "bg-brand-50 text-brand-700",
            )}
          >
            {entry.operation === "keep_selection"
              ? "KEEP"
              : entry.operation === "remove_residues" ||
                entry.operation === "remove_ligand"
                ? "REMOVE"
                : "ADD"}
          </span>
          <span className="min-w-0 text-[12px] font-medium text-ink">
            {entry.label}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onRemove(entry.id)}
            aria-label={`Remove ${entry.label}`}
          >
            <Minus className="size-3" />
          </Button>
        </div>
      ))}
    </div>
  );
}