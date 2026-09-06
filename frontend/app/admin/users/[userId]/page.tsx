"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, KeyRound, MailCheck } from "lucide-react";

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
  getUser,
  getUserAudit,
  sendCredentialLink,
  setUserActive,
  updateUser,
} from "@/lib/people";
import type { AdminUser, UserAuditEntry, UserRole } from "@/types/api";

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
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th>What</Th>
                  <Th>By</Th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} data-testid="audit-entry">
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
    <div className="space-y-4">
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
                        ? { role: form.role }
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
