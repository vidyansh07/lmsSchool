"use client";

/**
 * Roles: the six system roles with a lock, custom roles below, each with how
 * many people hold it. Opening a role is a read; New role is the only way in
 * to a write, and it happens on the builder's last step.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Grid3x3, Lock, Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { RequireAuth } from "@/components/require-auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { errorMessage } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import { formatDateTime } from "@/lib/format";
import { ROLE_LABEL } from "@/lib/labels";
import { deleteRole } from "@/lib/roles";
import type { RoleSummary } from "@/types/api";

function RolesList() {
  const { user } = useAuth();
  const params = useSearchParams();
  const mayManage = can(user?.capabilities, Capability.roleManage);
  const { data, error, isLoading, reload } =
    useApi<RoleSummary[]>("/api/v1/roles/");
  const [removing, setRemoving] = useState<RoleSummary | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(
    params.get("created")
      ? `Role "${params.get("created")}" created.`
      : params.get("saved")
        ? `Role "${params.get("saved")}" saved.`
        : null,
  );
  const [failure, setFailure] = useState<string | null>(null);
  const [isRemoving, setIsRemoving] = useState(false);

  async function remove() {
    if (!removing) return;
    setIsRemoving(true);
    try {
      await deleteRole(removing.slug, reason.trim());
      setNotice(
        `Role "${removing.name}" removed. It can be restored from the recycle bin.`,
      );
      setRemoving(null);
      setReason("");
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, "The role could not be removed."));
      setRemoving(null);
    } finally {
      setIsRemoving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Roles</h1>
          <p className="text-sm text-ink-muted">
            System roles are built in. A custom role is built from one of them
            and holds a different set of permissions, never a wider reach.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href="/admin/roles/matrix">
              <Grid3x3 className="size-4" aria-hidden="true" />
              Permission matrix
            </Link>
          </Button>
          {mayManage ? (
            <Button asChild>
              <Link href="/admin/roles/new">
                <Plus className="size-4" aria-hidden="true" />
                New role
              </Link>
            </Button>
          ) : null}
        </div>
      </div>

      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {failure ? <Alert variant="error">{failure}</Alert> : null}

      {isLoading ? (
        <LoadingState label="Loading roles…" rows={6} />
      ) : error ? (
        <ErrorState
          title="Could not load roles"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={reload}
        />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="No roles"
          description="The system roles have not been seeded."
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Role</Th>
                <Th>Built from</Th>
                <Th className="text-right">People</Th>
                <Th className="text-right">Permissions</Th>
                <Th>Status</Th>
                <Th>Updated</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {data.map((role) => (
                <tr key={role.slug} className="hover:bg-sunken/40">
                  <Td>
                    <Link
                      href={`/admin/roles/${role.slug}`}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {role.name}
                    </Link>
                    {role.is_system ? (
                      <Badge variant="neutral" className="ml-2">
                        <Lock className="mr-1 size-3" aria-hidden="true" />
                        System
                      </Badge>
                    ) : null}
                    {role.description ? (
                      <p className="text-xs text-ink-muted">
                        {role.description}
                      </p>
                    ) : null}
                  </Td>
                  <Td>{ROLE_LABEL[role.kind]}</Td>
                  <Td className="text-right tabular-nums">{role.user_count}</Td>
                  <Td className="text-right tabular-nums">
                    {role.permission_count}
                  </Td>
                  <Td>
                    <Badge
                      variant={role.status === "active" ? "success" : "neutral"}
                    >
                      {role.status === "active" ? "Active" : "Disabled"}
                    </Badge>
                  </Td>
                  <Td>{formatDateTime(role.updated_at)}</Td>
                  <Td className="text-right">
                    {mayManage && !role.is_system ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setFailure(null);
                          setRemoving(role);
                        }}
                      >
                        Remove
                      </Button>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}

      {removing ? (
        <Dialog
          open
          onOpenChange={(open) =>
            open ? undefined : (setRemoving(null), setReason(""))
          }
        >
          <DialogContent>
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                void remove();
              }}
            >
              <DialogHeader>
                <DialogTitle>Remove “{removing.name}”?</DialogTitle>
                <DialogDescription>
                  {removing.user_count > 0
                    ? `${removing.user_count} account(s) still hold this role. Move them to another role first.`
                    : "The role goes to the recycle bin and can be restored. Say why."}
                </DialogDescription>
              </DialogHeader>
              {removing.user_count === 0 ? (
                <Field label="Why remove it?" htmlFor="remove-reason">
                  <Input
                    id="remove-reason"
                    required
                    maxLength={255}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder="Replaced by Placement coordinator v2"
                  />
                </Field>
              ) : null}
              <DialogFooter>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setRemoving(null);
                    setReason("");
                  }}
                >
                  Keep it
                </Button>
                <Button
                  type="submit"
                  variant="destructive"
                  disabled={
                    isRemoving || removing.user_count > 0 || !reason.trim()
                  }
                >
                  {isRemoving ? "Removing…" : "Remove role"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  );
}

export default function RolesPage() {
  return (
    <RequireAuth>
      <Suspense fallback={<LoadingState label="Loading roles…" rows={6} />}>
        <RolesList />
      </Suspense>
    </RequireAuth>
  );
}
