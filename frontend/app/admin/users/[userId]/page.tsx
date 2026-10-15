"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, KeyRound, MailCheck } from "lucide-react";

import { UserSessionsCard } from "@/components/admin/user-sessions-card";
import { useAuth } from "@/components/auth-provider";
import { Confirm } from "@/components/confirm";
import { RequireAuth } from "@/components/require-auth";
import {
  isStepUpRequired,
  StepUpDialog,
} from "@/components/roles/step-up-dialog";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { ApiError, errorMessage, fieldErrors } from "@/lib/api";
import { Capability } from "@/lib/capabilities";
import { formatDateTime } from "@/lib/format";
import { ROLE_LABEL, ROLE_OPTIONS, labelFor } from "@/lib/labels";
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
  transitionUserRole,
  updateUser,
} from "@/lib/people";
import { useBranches } from "@/components/organisation/branch-field";
import { moveUserToBranch } from "@/lib/organisation";
import { useUnsavedChanges } from "@/hooks/use-unsaved-changes";
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

/** An audit entry's moment, or the fallback — never "Invalid Date". */
function formatWhen(value: string | null | undefined): string {
  return formatDateTime(value);
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
                  <Th className="sticky top-0 z-10 bg-sunken">When</Th>
                  <Th className="sticky top-0 z-10 bg-sunken">What</Th>
                  <Th className="sticky top-0 z-10 bg-sunken">By</Th>
                </tr>
              </thead>
              <tbody className="">
                {entries.map((entry) => (
                  <tr
                    key={entry.id}
                    data-testid="audit-entry"
                    className="animate-fade-in transition-colors hover:bg-sunken/40"
                  >
                    <Td className="whitespace-nowrap text-ink-muted">
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
                    <Td className="text-ink-muted">
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

export function UserAdministration({ userId }: { userId: string }) {
  const router = useRouter();
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
  const [roleDialogOpen, setRoleDialogOpen] = useState(false);
  const [roleReason, setRoleReason] = useState("");
  const [stepUpOpen, setStepUpOpen] = useState(false);
  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const [deactivateReason, setDeactivateReason] = useState("");
  const [deactivateError, setDeactivateError] = useState("");
  const hasUnsavedChanges = Boolean(
    user &&
      (form.email.trim().toLowerCase() !== user.email.toLowerCase() ||
        form.first_name.trim() !== user.first_name ||
        form.last_name.trim() !== user.last_name ||
        form.phone.trim() !== (user.phone ?? "") ||
        form.role !== user.role ||
        (form.custom_role || null) !== (user.custom_role ?? null)),
  );
  const {
    isPrompting: isDiscardPromptOpen,
    guard: guardNavigation,
    confirmDiscard,
    cancelDiscard,
  } = useUnsavedChanges(hasUnsavedChanges);

  function navigateWithGuard(href: string) {
    guardNavigation(() => router.push(href));
  }

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
  const roleChanged =
    form.role !== user.role ||
    (form.custom_role || null) !== (user.custom_role ?? null);
  const allowedRoleOptions = ROLE_OPTIONS.filter((option) =>
    user.allowed_role_transitions.includes(option.value),
  );

  async function applyRoleTransition() {
    if (!user || !roleChanged || !roleReason.trim()) return;
    setBusy("role");
    setErrors({});
    setNotice("");
    try {
      await transitionUserRole(user.id, {
        role: form.role,
        custom_role: form.custom_role || null,
        reason: roleReason.trim(),
      });
      setRoleDialogOpen(false);
      setRoleReason("");
      setNotice("Role changed. Their existing sessions were ended.");
      load();
    } catch (cause) {
      if (isStepUpRequired(cause)) {
        // The step-up is the confirmation the server asks for. The role
        // dialog steps aside so two modals never compete for focus, and its
        // selection and reason survive in state for the retry.
        setRoleDialogOpen(false);
        setStepUpOpen(true);
      } else {
        setErrors(fieldErrors(cause));
        setRoleDialogOpen(true);
      }
    } finally {
      setBusy("");
    }
  }

  async function deactivate() {
    if (!user || !deactivateReason.trim()) return;
    setBusy("active");
    setDeactivateError("");
    setNotice("");
    try {
      await setUserActive(user.id, false, deactivateReason.trim());
      setDeactivateOpen(false);
      setDeactivateReason("");
      setNotice("Deactivated. They were signed out everywhere and cannot sign in.");
      load();
    } catch (cause) {
      setDeactivateError(errorMessage(cause, "This account could not be deactivated."));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <div className="space-y-4">
      <Link
        href="/admin/users"
        onClick={(event) => {
          event.preventDefault();
          navigateWithGuard("/admin/users");
        }}
        className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All users
      </Link>

      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          {user.full_name || user.email}
        </h1>
        <Badge>{labelFor(ROLE_LABEL, user.role)}</Badge>
        <Badge variant={user.is_active ? "success" : "error"}>
          {user.is_active ? "Active" : "Inactive"}
        </Badge>
        <Badge variant={user.is_email_verified ? "success" : "warning"}>
          {user.is_email_verified ? "Email verified" : "Email unverified"}
        </Badge>
        {user.profile_type && user.profile_id ? (
          <Link
            href={
              user.profile_type === "student"
                ? `/students/${user.profile_id}`
                : `/manage/trainers/${user.profile_id}`
            }
            onClick={(event) => {
              event.preventDefault();
              navigateWithGuard(event.currentTarget.getAttribute("href") ?? "/admin/users");
            }}
            className="text-sm font-medium text-action hover:underline"
          >
            Open {user.profile_type === "student" ? "student 360" : "trainer profile"}
          </Link>
        ) : null}
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
          <CardTitle as="h2">Details</CardTitle>
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
                id="user-email"
                type="email"
                autoComplete="email"
                value={form.email}
                disabled={!mayAdminister}
                onChange={(event) =>
                  setForm({ ...form, email: event.target.value })
                }
              />
            </Field>
            <Field label="Phone" htmlFor="user-phone" error={errors.phone}>
              <Input
                id="user-phone"
                type="tel"
                autoComplete="tel"
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
                id="user-first"
                autoComplete="given-name"
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
                id="user-last"
                autoComplete="family-name"
                value={form.last_name}
                disabled={!mayAdminister}
                onChange={(event) =>
                  setForm({ ...form, last_name: event.target.value })
                }
              />
            </Field>
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

      {can(Capability.userChangeRole) && mayAdminister && !isSelf ? (
        <Card>
          <CardHeader>
            <CardTitle as="h2">Role and permissions</CardTitle>
            <CardDescription>
              Role changes are reviewed separately from contact details because they alter access.
              Student and trainer identities require a dedicated conversion workflow.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {errors.role || errors.custom_role || errors.reason ? (
              <Alert variant="error">
                {errors.role ?? errors.custom_role ?? errors.reason}
              </Alert>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="System role"
                htmlFor="user-role"
                hint="Only transitions approved by the server are offered."
              >
                <Select
                  id="user-role"
                  value={form.role}
                  onChange={(event) => {
                    setErrors({});
                    setForm({
                      ...form,
                      role: event.target.value as UserRole,
                      custom_role: "",
                    });
                  }}
                >
                  {allowedRoleOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <CustomRoleField
                kind={form.role}
                value={form.custom_role}
                error={errors.custom_role}
                onChange={(value) => setForm({ ...form, custom_role: value })}
              />
            </div>
            {form.role === "student" || form.role === "trainer" ? (
              <Alert variant="info">
                This account keeps its {labelFor(ROLE_LABEL, form.role).toLowerCase()} identity.
                Converting it to a different persona is intentionally unavailable here so academic
                history and profile access cannot become inconsistent.
              </Alert>
            ) : null}
            <Button
              type="button"
              variant="outline"
              disabled={!roleChanged || busy === "role"}
              onClick={() => setRoleDialogOpen(true)}
            >
              Review role change
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Dialog
        open={roleDialogOpen}
        onOpenChange={(open) => (busy === "role" ? null : setRoleDialogOpen(open))}
      >
        <DialogContent size="md" hideCloseButton>
          <DialogHeader>
            <DialogTitle>Change this account&rsquo;s role?</DialogTitle>
            <DialogDescription>
              This changes their permissions immediately and ends every session established under
              the previous role.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {errors.role || errors.custom_role || errors.user || errors.__all__ ? (
              <Alert variant="error">
                {errors.role ?? errors.custom_role ?? errors.user ?? errors.__all__}
              </Alert>
            ) : null}
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge>{labelFor(ROLE_LABEL, user.role)}</Badge>
              <span className="text-ink-muted" aria-hidden="true">→</span>
              <Badge variant="warning">{labelFor(ROLE_LABEL, form.role)}</Badge>
            </div>
            <Alert variant="warning">
              Existing sessions will end. Capabilities and centre-scoped access may change on the
              next sign-in. The person&rsquo;s domain record is not converted by this action.
            </Alert>
            <Field
              label="Reason for change"
              htmlFor="role-change-reason"
              hint="Required and recorded in the account history."
              error={errors.reason}
              required
            >
              <Input
                id="role-change-reason"
                value={roleReason}
                maxLength={255}
                onChange={(event) => setRoleReason(event.target.value)}
              />
            </Field>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={busy === "role"}
              onClick={() => setRoleDialogOpen(false)}
            >
              Go back
            </Button>
            <Button
              type="button"
              disabled={busy === "role" || !roleReason.trim()}
              onClick={() => void applyRoleTransition()}
            >
              {busy === "role" ? "Changing…" : "Change role"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deactivateOpen}
        onOpenChange={(open) => (busy === "active" ? null : setDeactivateOpen(open))}
      >
        <DialogContent size="md" hideCloseButton>
          <DialogHeader>
            <DialogTitle>Deactivate {user.full_name || user.email}?</DialogTitle>
            <DialogDescription>
              They are signed out of every device at once and cannot sign in until somebody
              activates the account again. Nothing they did is deleted.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {deactivateError ? <Alert variant="error">{deactivateError}</Alert> : null}
            <Field
              label="Reason"
              htmlFor="deactivate-reason"
              hint="Required and recorded in the account history."
              required
            >
              <Input
                id="deactivate-reason"
                value={deactivateReason}
                maxLength={255}
                onChange={(event) => setDeactivateReason(event.target.value)}
              />
            </Field>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={busy === "active"}
              onClick={() => setDeactivateOpen(false)}
            >
              Keep active
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={busy === "active" || !deactivateReason.trim()}
              onClick={() => void deactivate()}
            >
              {busy === "active" ? "Deactivating…" : "Deactivate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <StepUpDialog
        open={stepUpOpen}
        onConfirmed={() => {
          setStepUpOpen(false);
          void applyRoleTransition();
        }}
        onCancel={() => {
          setStepUpOpen(false);
          setRoleDialogOpen(true);
        }}
      />

      {mayAdminister && user.role !== "superadmin" ? (
        <CentreCard user={user} busy={busy} run={run} errors={errors} />
      ) : null}

      {mayAdminister && user.role !== "superadmin" ? (
        <ScopeGrantsCard userId={user.id} />
      ) : null}

      {/* Devices and addresses follow the same ladder as everything else on
          this screen: the server refuses them for an account above yours. */}
      {can(Capability.sessionViewAny) && mayAdminister ? (
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
            <p className="text-sm text-ink-muted">
              Nobody here sets somebody else&rsquo;s password. A link goes to
              the account holder, and they choose it — so only one person ever
              knows it, and the record says they set it.
            </p>

            {can(Capability.userSetActive) && mayAdminister && !isSelf ? (
              <div className="border-t border-line pt-3">
                <Button
                  type="button"
                  variant={user.is_active ? "destructive" : "primary"}
                  disabled={busy === "active"}
                  onClick={() => {
                    if (user.is_active) {
                      // Locking somebody out is asked first, with a reason
                      // for the audit trail; letting them back in is not.
                      setDeactivateError("");
                      setDeactivateOpen(true);
                      return;
                    }
                    void run(
                      "active",
                      () => setUserActive(user.id, true),
                      "Activated.",
                    );
                  }}
                >
                  {user.is_active
                    ? "Deactivate this account"
                    : "Activate this account"}
                </Button>
                <p className="mt-2 text-sm text-ink-muted">
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
      <Confirm
        open={isDiscardPromptOpen}
        title="Discard unsaved account changes?"
        description="The details or role selection on this page have not been saved."
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        isConfirming={false}
        onConfirm={confirmDiscard}
        onCancel={cancelDiscard}
      />
    </>
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
          <p className="text-sm text-ink-muted">No direct grants.</p>
        ) : (
          <ul className="space-y-2">
            {grants.map((grant) => (
              <li
                key={grant.id}
                className="flex items-center justify-between rounded-md border border-line px-3 py-2 text-sm"
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
      hint={`A configured ${labelFor(ROLE_LABEL, kind).toLowerCase()} role replaces the default set of permissions.`}
    >
      <Select
        id="user-custom-role"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">
          Default {labelFor(ROLE_LABEL, kind).toLowerCase()} permissions
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
