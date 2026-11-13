import { useMemo, useState } from "react";
import { ScrollText, ShieldQuestion } from "lucide-react";
import { useAdminAudit } from "../lib/queries";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { Badge } from "../components/ui/Badge";
import { Select } from "../components/ui/Form";
import { formatRelative } from "../lib/utils";
import type { AdminAuditEntry } from "../lib/types";

const ACTION_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "job.create", label: "Job created" },
  { value: "job.cancel", label: "Job canceled" },
  { value: "job.claim", label: "Job claimed" },
  { value: "job.finish", label: "Job finished" },
  { value: "job.retry", label: "Job retried" },
  { value: "job.retention_delete", label: "Job deleted (retention)" },
  { value: "user.register", label: "Account registered" },
  { value: "user.update", label: "Account updated" },
  { value: "user.admin_update", label: "Account changed by admin" },
  { value: "session.login", label: "Signed in" },
  { value: "rate_limit.denied", label: "Rate limit hit" },
];

const OUTCOME_OPTIONS = [
  "accepted",
  "denied",
  "requested",
  "success",
  "canceled",
  "claimed",
  "queued",
  "deleted",
];

function outcomeTone(outcome: string): "green" | "rose" | "amber" | "neutral" {
  switch (outcome) {
    case "accepted":
    case "success":
    case "claimed":
    case "queued":
      return "green";
    case "denied":
      return "rose";
    case "requested":
    case "canceled":
      return "amber";
    default:
      return "neutral";
  }
}

function shortTarget(entry: AdminAuditEntry): string {
  if (!entry.target_type) return "—";
  const id = entry.target_id ?? "";
  return `${entry.target_type}: ${id.length > 8 ? `${id.slice(0, 8)}…` : id}`;
}

/**
 * The append-only audit trail.  Authentication and rate-limit denials are
 * deliberately logged to the structured log instead, so this table is the
 * record of every *accepted* control-plane action — who did what, to what,
 * and from where.
 */
export function AdminAuditPage() {
  const [action, setAction] = useState("");
  const [outcome, setOutcome] = useState("");

  const audit = useAdminAudit({
    action: action || null,
    outcome: outcome || null,
    limit: 50,
  });

  const entries = useMemo(
    () =>
      audit.data?.pages.flatMap(
        (page: { items: AdminAuditEntry[] }) => page.items,
      ) ?? [],
    [audit.data],
  );

  const filtersActive = Boolean(action) || Boolean(outcome);

  return (
    <div>
      <PageHeader
        eyebrow="Administration"
        title="Audit log"
        description="Every accepted control-plane action, newest first — who did what, to what, and from where. Authentication and rate-limit denials are in the structured log, not here."
      />

      <Card className="mt-6 overflow-hidden">
        <CardHeader
          title="All entries"
          description={`${entries.length} loaded${filtersActive ? " with filters" : ""}`}
          action={
            filtersActive ? (
              <button
                type="button"
                onClick={() => {
                  setAction("");
                  setOutcome("");
                }}
                className="rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-muted transition hover:bg-ink/5 hover:text-ink"
              >
                Clear filters
              </button>
            ) : null
          }
        />

        <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3">
          <Select
            aria-label="Filter by action"
            className="w-52"
            value={action}
            onChange={(event) => setAction(event.target.value)}
          >
            <option value="">All actions</option>
            {ACTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Filter by outcome"
            className="w-40"
            value={outcome}
            onChange={(event) => setOutcome(event.target.value)}
          >
            <option value="">All outcomes</option>
            {OUTCOME_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
        </div>

        {audit.isLoading ? (
          <div className="divide-y divide-line">
            {[0, 1, 2, 3].map((item) => (
              <div key={item} className="animate-pulse px-5 py-3.5">
                <div className="h-3 w-40 rounded bg-line" />
                <div className="mt-2 h-2.5 w-64 rounded bg-line" />
              </div>
            ))}
          </div>
        ) : audit.isError ? (
          <p className="px-5 py-8 text-center text-[12.5px] text-rose-600">
            {audit.error instanceof Error
              ? audit.error.message
              : "Could not load the audit log."}
          </p>
        ) : entries.length === 0 ? (
          <EmptyState
            icon={<ShieldQuestion className="size-5" />}
            title={filtersActive ? "Nothing matches these filters" : "No entries yet"}
            description={
              filtersActive
                ? "Try clearing the filters to see the whole trail."
                : "Actions will appear here as accounts use the deployment."
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-left">
              <thead>
                <tr className="text-[10.5px] font-semibold uppercase tracking-[0.13em] text-faint">
                  <th className="px-5 py-2.5">When</th>
                  <th className="px-3 py-2.5">Account</th>
                  <th className="px-3 py-2.5">Action</th>
                  <th className="px-3 py-2.5">Outcome</th>
                  <th className="px-3 py-2.5">Target</th>
                  <th className="px-3 py-2.5">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {entries.map((entry) => (
                  <tr key={entry.id} className="align-top">
                    <td className="whitespace-nowrap px-5 py-2.5 text-[11.5px] text-muted" title={entry.created_at}>
                      {formatRelative(entry.created_at)}
                    </td>
                    <td className="px-3 py-2.5 text-[12px] font-medium text-ink">
                      {entry.owner_email ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-[11px] text-muted" title={entry.action}>
                      {ACTION_OPTIONS.find((option) => option.value === entry.action)?.label ??
                        entry.action}
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge tone={outcomeTone(entry.outcome)}>{entry.outcome}</Badge>
                    </td>
                    <td className="px-3 py-2.5 text-[11px] text-muted" title={entry.target_id ?? undefined}>
                      {shortTarget(entry)}
                    </td>
                    <td className="px-3 py-2.5 text-[11px] text-faint">
                      {entry.remote_addr ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {entries.length > 0 && !audit.isError ? (
          <div className="flex items-center justify-between border-t border-line px-5 py-3">
            <span className="inline-flex items-center gap-1.5 text-[11px] text-faint">
              <ScrollText className="size-3" />
              Newest first · {entries.length} loaded
            </span>
            {audit.hasNextPage ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void audit.fetchNextPage()}
                disabled={audit.isFetchingNextPage}
              >
                {audit.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            ) : (
              <span className="text-[11px] font-medium text-faint">
                End of the trail
              </span>
            )}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
