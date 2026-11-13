import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield, Users } from "lucide-react";
import * as api from "../lib/api";
import type { AdminUserInfo } from "../lib/types";
import { PageHeader } from "../components/layout/PageHeader";
import { Badge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);

  const accounts = useQuery({
    queryKey: ["admin", "users"],
    queryFn: api.listUsers,
  });

  const update = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: api.AdminUserUpdate;
    }) => api.adminUpdateUser(id, payload),
    onSuccess: (updated) => {
      setNotice(
        `${updated.first_name} ${updated.last_name} was updated.`,
      );
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (error) => {
      setNotice(
        error instanceof Error ? error.message : "The change was rejected.",
      );
    },
  });

  const items = accounts.data ?? [];

  return (
    <div>
      <PageHeader
        eyebrow="Administration"
        title="Accounts"
        description={`${items.length} account${items.length !== 1 ? "s" : ""} on this server. Each account owns its own uploads, simulations, and preparations.`}
      />

      {notice ? (
        <p className="mt-4 rounded-lg bg-brand-50 px-3 py-2 text-[13px] font-medium text-brand-800 ring-1 ring-inset ring-brand-200/70">
          {notice}
        </p>
      ) : null}

      <Card className="mt-6 overflow-hidden">
        <CardHeader
          title="All accounts"
          description="Deactivating an account signs it out and blocks new sign-ins. The data it produced is kept."
        />

        {accounts.isLoading ? (
          <div className="divide-y divide-line">
            {[0, 1, 2].map((item) => (
              <div key={item} className="animate-pulse px-5 py-4">
                <div className="h-3 w-48 rounded bg-line" />
                <div className="mt-2 h-2.5 w-32 rounded bg-line" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Users className="size-5" />}
            title="No accounts"
            description="Nobody has signed up yet."
          />
        ) : (
          <div className="divide-y divide-line">
            {items.map((account) => (
              <UserRow
                key={account.id}
                account={account}
                pending={update.isPending}
                onToggleActive={() =>
                  update.mutate({
                    id: account.id,
                    payload: { is_active: !account.is_active },
                  })
                }
                onToggleAdmin={() =>
                  update.mutate({
                    id: account.id,
                    payload: { is_admin: !account.is_admin },
                  })
                }
              />
            ))}
          </div>
        )}
      </Card>

      {accounts.isError ? (
        <p className="mt-3 text-[12px] text-rose-600">
          {accounts.error instanceof Error
            ? accounts.error.message
            : "Could not load the accounts."}
        </p>
      ) : null}
    </div>
  );
}

function UserRow({
  account,
  pending,
  onToggleActive,
  onToggleAdmin,
}: {
  account: AdminUserInfo;
  pending: boolean;
  onToggleActive: () => void;
  onToggleAdmin: () => void;
}) {
  const initials = `${account.first_name.charAt(0)}${account.last_name.charAt(0)}`.toUpperCase();

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[11px] font-semibold text-brand-800">
        {initials}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-[13.5px] font-medium text-ink">
          {account.first_name} {account.last_name}
        </p>
        <p className="mt-0.5 truncate text-[11px] text-faint">
          {account.email} · joined{" "}
          {new Date(account.created_at).toLocaleDateString()}
        </p>
      </div>

      <div className="flex items-center gap-1.5">
        {account.is_admin ? (
          <Badge tone="violet" dot>
            Administrator
          </Badge>
        ) : null}
        <Badge tone={account.is_active ? "green" : "neutral"} dot>
          {account.is_active ? "Active" : "Deactivated"}
        </Badge>
      </div>

      <span className="text-[11px] text-faint tabular-nums">
        {account.usage.jobs} job{account.usage.jobs !== 1 ? "s" : ""} ·{" "}
        {account.usage.files} file{account.usage.files !== 1 ? "s" : ""}
      </span>

      <div className="flex items-center gap-1.5">
        <Button
          variant="secondary"
          size="sm"
          disabled={pending}
          onClick={onToggleActive}
        >
          {account.is_active ? "Deactivate" : "Activate"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={pending}
          onClick={onToggleAdmin}
          leadingIcon={<Shield className="size-3.5" />}
        >
          {account.is_admin ? "Revoke admin" : "Make admin"}
        </Button>
      </div>
    </div>
  );
}
