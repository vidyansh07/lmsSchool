"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, KeyRound, MailCheck } from "lucide-react";

import { UserSessionsCard } from "@/components/admin/user-sessions-card";
import { useAuth } from "@/components/auth-provider";
import { RequireAuth } from "@/components/require-auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { ApiError, fieldErrors } from "@/lib/api";
import { Capability } from "@/lib/capabilities";
import { ROLE_LABEL, ROLE_OPTIONS } from "@/lib/labels";
import {
  listRoles,
  listScopeGrants,
  grantScope,
  revokeScope,
  type ScopeGrantRow,
} from "@/lib/roles";
import {
  getUser,
  getUserAudit,
  sendCredentialLink,
  setUserActive,
  updateUser,
} from "@/lib/people";
import { useBranches } from "@/components/organisation/branch-field";
import { moveUserToBranch } from "@/lib/organisation";
import type {
  AdminUser,
  RoleSummary,
  UserAuditEntry,
  UserRole,
} from "@/types/api";

/**
 * Administering one account.
 *
 * The list screen could only activate and deactivate, so nobody — not even a
 * superadmin — could correct a name or a role without a database shell. This is
 * the screen the role hierarchy always implied.
 *
 * Which fields appear is not decided here. The server decides who may
 * administer whom, and answers 403 when the answer is no; this page asks for
 * what it wants and reports what it is told. Hiding a control is a courtesy to
 * the person using it, never the thing that enforces the rule.
 */

function formatWhen(value: string): string {
  return new Date(value).toLocaleString();
}

/** The account's own history, on the same screen as the fields it explains. */
function History({ userId }: { userId: string }) {
  const { can } = useAuth();
  const [entries, setEntries] = useState<UserAuditEntry[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!can(Capability.auditView)) return;
    let cancelled = false;
    getUserAudit(userId)
      .then((rows) => {
        if (!cancelled) setEntries(rows);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, can]);

  if (!can(Capability.auditView)) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>History</CardTitle>
        <CardDescription>
          What has been done to this account, most recent first. Asked at the
          moment somebody notices a change, so it lives here rather than in a
          separate tool.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {failed ? (
          <Alert variant="error">
            Could not load this account&rsquo;s history.
          </Alert>
        ) : null}
        {entries === null && !failed ? (
          <LoadingState label="Loading history…" rows={3} />
        ) : null}
        {entries?.length === 0 ? (
          <EmptyState
            title="Nothing recorded yet"
            description="No change has been made to this account."
          />
        ) : null}
        {entries && entries.length > 0 ? (
          <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
            <Table>
              <thead>
                <tr>
                  <Th className="sticky top-0 z-10 bg-muted">When</Th>
                  <Th className="sticky top-0 z-10 bg-muted">What</Th>
                  <Th className="sticky top-0 z-10 bg-muted">By</Th>
                </tr>
              </thead>
              <tbody className="stagger">
                {entries.map((entry) => (
                  <tr
                    key={entry.id}
                    data-testid="audit-entry"
                    className="animate-fade-in transition-colors hover:bg-muted/40"
                  >
                    <Td className="whitespace-nowrap text-muted-foreground">
                      {formatWhen(entry.created_at)}
                    </Td>
                    <Td>
                      {entry.action_label}
                      {entry.result !== "success" ? (
                        <Badge variant="warning" className="ml-2">
                          {entry.result}
                        </Badge>
                      ) : null}
                    </Td>
                    <Td className="text-muted-foreground">
                      {entry.actor_label || "—"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
        ) : null}
      </CardContent>
    </Card>
  );
}

function UserAdministration({ userId }: { userId: string }) {
  const { user: currentUser, can } = useAuth();
  const [user, setUser] = useState<AdminUser | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [form, setForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    phone: "",
    role: "student" as UserRole,
    custom_role: "" as string,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    getUser(userId)
      .then((row) => {
        setUser(row);
        setForm({
          email: row.email,
          first_name: row.first_name,
          last_name: row.last_name,
          phone: row.phone ?? "",
          role: row.role,
          custom_role: row.custom_role ?? "",
        });
      })
      .catch((cause: unknown) =>
        setError(cause instanceof ApiError ? cause : null),
      );
  }, [userId]);

  useEffect(load, [load]);

  async function run(key: string, work: () => Promise<unknown>, said: string) {
    setBusy(key);
    setErrors({});
    setNotice("");
    try {
      await work();
      setNotice(said);
      load();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setBusy("");
    }
  }

  if (error) {
    return (
      <ErrorState
        title={
          error.status === 403
            ? "Not your account to administer"
            : "Could not load this user"
        }
        message={
          error.status === 403
            ? "You do not have authority over this account."
            : error.message
        }
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!user) return <LoadingState label="Loading account…" rows={6} />;

  const isSelf = user.id === currentUser?.id;
  const emailChanged =
    form.email.trim().toLowerCase() !== user.email.toLowerCase();
  // The server's answer, not a guess from capabilities. Viewing is wider than
  // administering — an administrator may see that a superadmin exists — and
  // without asking we would offer controls that cannot work.
  const mayAdminister = user.can_administer;

  return (
    <div className="animate-rise-in space-y-4">
      <Link
        href="/admin/users"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All users
      </Link>

      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          {user.full_name || user.email}
        </h1>
        <Badge>{ROLE_LABEL[user.role]}</Badge>
        <Badge variant={user.is_active ? "success" : "error"}>
          {user.is_active ? "Active" : "Inactive"}
        </Badge>
        <Badge variant={user.is_email_verified ? "success" : "warning"}>
          {user.is_email_verified ? "Email verified" : "Email unverified"}
        </Badge>
      </div>

      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}
      {errors.__all__ || errors.user ? (
        <Alert variant="error">{errors.user ?? errors.__all__}</Alert>
      ) : null}

      {!mayAdminister ? (
        <Alert variant="warning">
          You can see this account but not change it. Authority runs downward:
          you may administer accounts that hold less than your own, and not your
          peers or anybody above you.
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
          <CardDescription>
            Everything about this account that an administrator may set.
            Changing the email address signs the account out and sends a fresh
            verification link — it is the login identifier, not a contact field.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Email"
              htmlFor="user-email"
              error={errors.email}
              required
            >
              <Input
                type="email"
                value={form.email}
                disabled={!mayAdminister}
                onChange={(event) =>
                  setForm({ ...form, email: event.target.value })
                }
              />
            </Field>
            <Field label="Phone" htmlFor="user-phone" error={errors.phone}>
              <Input
                value={form.phone}
                disabled={!mayAdminister}
                onChange={(event) =>
                  setForm({ ...form, phone: event.target.value })
                }
              />
            </Field>
            <Field
              label="First name"
              htmlFor="user-first"
              error={errors.first_name}
              required
            >
              <Input
                value={form.first_name}
                disabled={!mayAdminister}
                onChange={(event) =>
                  setForm({ ...form, first_name: event.target.value })
                }
              />
            </Field>
            <Field
              label="Last name"
              htmlFor="user-last"
              error={errors.last_name}
            >
              <Input
                value={form.last_name}
                disabled={!mayAdminister}
                onChange={(event) =>
                  setForm({ ...form, last_name: event.target.value })
                }
              />
            </Field>
            {can(Capability.userChangeRole) && mayAdminister && !isSelf ? (
              <Field
                label="Role"
                htmlFor="user-role"
                error={errors.role}
                hint="You can only grant a role that holds no more than your own."
              >
                <Select
                  value={form.role}
                  onChange={(event) =>
                    setForm({ ...form, role: event.target.value as UserRole })
                  }
                >
                  {ROLE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}
            {can(Capability.userChangeRole) && mayAdminister && !isSelf ? (
              <CustomRoleField
                kind={form.role}
                value={form.custom_role}
                error={errors.custom_role}
                onChange={(value) => setForm({ ...form, custom_role: value })}
              />
            ) : null}
          </div>

          {emailChanged ? (
            <Alert variant="warning">
              Saving will sign this account out everywhere and mark the new
              address unverified until its owner confirms it.
            </Alert>
          ) : null}

          {mayAdminister ? (
            <Button
              type="button"
              disabled={busy === "save"}
              onClick={() =>
                void run(
                  "save",
                  () =>
                    updateUser(user.id, {
                      email: form.email.trim(),
                      first_name: form.first_name.trim(),
                      last_name: form.last_name.trim(),
                      phone: form.phone.trim(),
                      ...(can(Capability.userChangeRole) && !isSelf
                        ? {
                            role: form.role,
                            custom_role: form.custom_role || null,
                          }
                        : {}),
                    }),
                  "Saved.",
                )
              }
            >
              {busy === "save" ? "Saving…" : "Save changes"}
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {mayAdminister && user.role !== "superadmin" ? (
        <CentreCard user={user} busy={busy} run={run} errors={errors} />
      ) : null}

      {mayAdminister && user.role !== "superadmin" ? (
        <ScopeGrantsCard userId={user.id} />
      ) : null}

      {can(Capability.sessionViewAny) ? (
        <UserSessionsCard userId={user.id} />
      ) : null}

      {mayAdminister ? (
        <Card>
          <CardHeader>
            <CardTitle>Access</CardTitle>
            <CardDescription>
              Getting somebody back into their account, without anybody else
              learning their password.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={busy === "reset"}
                onClick={() =>
                  void run(
                    "reset",
                    () => sendCredentialLink(user.id, "password_reset"),
                    "A password-reset link has been sent to their address.",
                  )
                }
              >
                <KeyRound className="size-4" aria-hidden="true" />
                Send a password-reset link
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy === "verify" || user.is_email_verified}
                onClick={() =>
                  void run(
                    "verify",
                    () => sendCredentialLink(user.id, "email_verification"),
                    "A verification link has been sent to their address.",
                  )
                }
              >
                <MailCheck className="size-4" aria-hidden="true" />
                Resend the verification link
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              Nobody here sets somebody else&rsquo;s password. A link goes to
              the account holder, and they choose it — so only one person ever
              knows it, and the record says they set it.
            </p>

            {can(Capability.userSetActive) && mayAdminister && !isSelf ? (
              <div className="border-t border-border pt-3">
                <Button
                  type="button"
                  variant={user.is_active ? "destructive" : "primary"}
                  disabled={busy === "active"}
                  onClick={() =>
                    void run(
                      "active",
                      () => setUserActive(user.id, !user.is_active),
                      user.is_active
                        ? "Deactivated. Their next request will be refused."
                        : "Activated.",
                    )
                  }
                >
                  {user.is_active
                    ? "Deactivate this account"
                    : "Activate this account"}
                </Button>
                <p className="mt-2 text-sm text-muted-foreground">
                  {user.is_active
                    ? "Deactivating takes effect immediately and ends every session they have open."
                    : "They will be able to sign in again straight away."}
                </p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <History userId={user.id} />
    </div>
  );
}

/**
 * Which centre an account is bounded to, and the one control that changes it.
 *
 * Moving somebody is its own audited action server-side, not a field on the
 * details form, because it is the only edit that changes what a person can
 * *see* rather than what they are. Shown only to a caller who may assign
 * users to centres; the select lists the centres *they* may see, so a
 * bounded administrator cannot move somebody out of their own centre.
 */
function CentreCard({
  user,
  busy,
  run,
  errors,
}: {
  user: AdminUser;
  busy: string;
  run: (
    key: string,
    work: () => Promise<unknown>,
    said: string,
  ) => Promise<void>;
  errors: Record<string, string>;
}) {
  const { can } = useAuth();
  const mayMove = can(Capability.organisationAssignUsers);
  const { branches } = useBranches(mayMove);
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const others = branches.filter((branch) => branch.id !== user.branch_id);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Centre</CardTitle>
        <CardDescription>
          {user.branch_name
            ? `Bounded to ${user.branch_name} (${user.branch_code}). What they can see stops at its edge.`
            : "Not placed in any centre. Under the fail-closed rule this account sees nothing until it is."}
        </CardDescription>
      </CardHeader>
      {mayMove ? (
        <CardContent className="space-y-3">
          {errors.branch_id ? (
            <Alert variant="error">{errors.branch_id}</Alert>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
            <Field label="Move to" htmlFor="user-branch">
              <Select
                id="user-branch"
                value={target}
                onChange={(event) => setTarget(event.target.value)}
              >
                <option value="">Choose a centre</option>
                {others.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name} ({branch.code})
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Reason"
              htmlFor="user-branch-reason"
              hint="Kept in the audit trail."
            >
              <Input
                id="user-branch-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </Field>
            <Button
              type="button"
              variant="outline"
              disabled={busy === "branch" || target === ""}
              onClick={() =>
                void run(
                  "branch",
                  () => moveUserToBranch(user.id, target, reason.trim()),
                  "Moved to the other centre.",
                ).then(() => {
                  setTarget("");
                  setReason("");
                })
              }
            >
              Move
            </Button>
          </div>
        </CardContent>
      ) : null}
    </Card>
  );
}

/**
 * Batches or courses this person was granted directly (ADR-02) — needed only
 * when their role's scope on a capability has been narrowed to `assigned`,
 * but shown here unconditionally since granting ahead of time is harmless
 * and the alternative (guessing whether it currently matters) is worse.
 */
function ScopeGrantsCard({ userId }: { userId: string }) {
  const [grants, setGrants] = useState<ScopeGrantRow[] | null>(null);
  const [batchId, setBatchId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listScopeGrants(userId)
      .then(setGrants)
      .catch(() => setGrants([]));
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  async function addGrant(event: React.FormEvent) {
    event.preventDefault();
    if (!batchId.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await grantScope(userId, { batch: batchId.trim() });
      setBatchId("");
      load();
    } catch (cause) {
      setError(fieldErrors(cause).batch ?? "That batch could not be granted.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(grantId: string) {
    setBusy(true);
    try {
      await revokeScope(userId, grantId);
      load();
    } finally {
      setBusy(false);
    }
  }

  if (grants === null) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Scope grants</CardTitle>
        <CardDescription>
          Batches or courses this account may reach directly, on top of what
          their role already sees. Only matters when a permission on their role
          is narrowed to &ldquo;assigned&rdquo;.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? <Alert variant="error">{error}</Alert> : null}
        {grants.length === 0 ? (
          <p className="text-sm text-muted-foreground">No direct grants.</p>
        ) : (
          <ul className="space-y-2">
            {grants.map((grant) => (
              <li
                key={grant.id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
              >
                <span>
                  {grant.batch_code
                    ? `${grant.batch_code} · ${grant.batch_name}`
                    : `${grant.course_code} · ${grant.course_title}`}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => void remove(grant.id)}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={addGrant} className="flex flex-wrap items-end gap-2">
          <Field label="Batch ID" htmlFor="scope-grant-batch">
            <Input
              id="scope-grant-batch"
              placeholder="Batch UUID"
              value={batchId}
              onChange={(event) => setBatchId(event.target.value)}
            />
          </Field>
          <Button type="submit" disabled={busy || !batchId.trim()}>
            Grant batch
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function UserAdministrationPage({
  params,
}: {
  params: Promise<{ userId: string }>;
}) {
  const { userId } = use(params);
  return (
    <RequireAuth capability={Capability.userViewAny}>
      <UserAdministration userId={userId} />
    </RequireAuth>
  );
}

/**
 * The configured roles of the account's kind (ADR-01). Loaded once when the
 * field mounts — a read — and offered only when at least one exists, so the
 * common case stays one dropdown.
 */
function CustomRoleField({
  kind,
  value,
  error,
  onChange,
}: {
  kind: UserRole;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  const [roles, setRoles] = useState<RoleSummary[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    listRoles()
      .then((rows) => {
        if (!cancelled) setRoles(rows);
      })
      .catch(() => {
        if (!cancelled) setRoles([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const options = (roles ?? []).filter(
    (row) => !row.is_system && row.kind === kind && row.status === "active",
  );
  if (roles === null || (options.length === 0 && !value)) return null;
  return (
    <Field
      label="Custom role"
      htmlFor="user-custom-role"
      error={error}
      hint={`A configured ${ROLE_LABEL[kind].toLowerCase()} role replaces the default set of permissions.`}
    >
      <Select
        id="user-custom-role"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">
          Default {ROLE_LABEL[kind].toLowerCase()} permissions
        </option>
        {options.map((row) => (
          <option key={row.slug} value={row.slug}>
            {row.name}
          </option>
        ))}
      </Select>
    </Field>
  );
}
