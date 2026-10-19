"use client";

/**
 * "Getting in": where an account stands between being created and its owner
 * signing in — the invitation, the password, the email, two-factor — and the
 * one next step that helps, with an honest answer about whether the email
 * went. The mail service's own wording never appears; the server translates
 * it (`apps.accounts.emails.describe_failure`).
 */

import { KeyRound, MailCheck, Send } from "lucide-react";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { sendCredentialLink } from "@/lib/people";
import type { AdminUserRecord } from "@/types/api";

export function GettingInCard({
  user,
  mayManage,
  onSent,
}: {
  user: AdminUserRecord;
  /** May send password and verification links (administers the account
   *  and holds `user.update_any`). An unaccepted invitation is offered on
   *  `user.may_send_invitation` as well. */
  mayManage: boolean;
  onSent: () => void;
}) {
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function send(key: string, action: "password_reset" | "email_verification") {
    setBusy(key);
    setResult(null);
    try {
      const answer = await sendCredentialLink(user.id, action);
      setResult({ ok: answer.sent, text: answer.detail });
      onSent();
    } catch (cause) {
      setResult({ ok: false, text: errorMessage(cause, "Could not send the email.") });
    } finally {
      setBusy("");
    }
  }

  const accepted = user.invitation_accepted;
  const invitation = user.invitation;
  const last = user.last_account_email;
  const mayInvite = !accepted && user.is_active && (user.may_send_invitation || mayManage);

  const facts: [string, React.ReactNode][] = [
    [
      "Password",
      accepted ? (
        <Badge variant="success">Set by them</Badge>
      ) : (
        <Badge variant="warning">Not set yet</Badge>
      ),
    ],
    [
      "Invitation",
      accepted
        ? "Accepted"
        : invitation
          ? invitation.expired
            ? `Expired ${formatDateTime(invitation.expires_at)}`
            : `Sent ${formatDateTime(invitation.sent_at)} · works until ${formatDateTime(invitation.expires_at)}`
          : "None sent",
    ],
    ["Last sign-in", user.last_login ? formatDateTime(user.last_login) : "Never"],
    [
      "Email",
      user.is_email_verified ? (
        <Badge variant="success">Verified</Badge>
      ) : (
        <Badge variant="warning">Not verified</Badge>
      ),
    ],
    ["Two-factor", user.mfa_enabled ? "On" : "Off"],
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle as="h2">Getting in</CardTitle>
        <CardDescription>
          From the invitation to their first sign-in. Nobody here sets another person&rsquo;s
          password: a link goes to them and they choose it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-3">
          {facts.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-2xs font-medium uppercase tracking-wide text-ink-faint">{label}</dt>
              <dd className="text-sm text-ink">{value}</dd>
            </div>
          ))}
        </dl>

        {last ? (
          last.sent ? (
            <p className="text-sm text-ink-muted">
              Last account email: {last.kind_label.toLowerCase()}, {formatDateTime(last.at)} — handed
              to the mail service.
            </p>
          ) : (
            <Alert variant="warning">
              The last account email ({last.kind_label.toLowerCase()}, {formatDateTime(last.at)}) was
              not sent. {last.error}
            </Alert>
          )
        ) : null}

        {result ? <Alert variant={result.ok ? "success" : "error"}>{result.text}</Alert> : null}

        <div className="flex flex-wrap gap-2">
          {mayInvite ? (
            <Button
              type="button"
              disabled={busy !== ""}
              onClick={() => void send("invite", "password_reset")}
            >
              <Send className="size-4" aria-hidden="true" />
              {busy === "invite" ? "Sending…" : invitation ? "Send a new invitation" : "Send the invitation"}
            </Button>
          ) : null}
          {accepted && mayManage && user.is_active ? (
            <Button
              type="button"
              variant="outline"
              disabled={busy !== ""}
              onClick={() => void send("reset", "password_reset")}
            >
              <KeyRound className="size-4" aria-hidden="true" />
              {busy === "reset" ? "Sending…" : "Send a password-reset link"}
            </Button>
          ) : null}
          {accepted && mayManage && user.is_active && !user.is_email_verified ? (
            <Button
              type="button"
              variant="outline"
              disabled={busy !== ""}
              onClick={() => void send("verify", "email_verification")}
            >
              <MailCheck className="size-4" aria-hidden="true" />
              {busy === "verify" ? "Sending…" : "Send a verification link"}
            </Button>
          ) : null}
        </div>
        {!user.is_active ? (
          <p className="text-sm text-ink-muted">The account is inactive; reactivate it to send links.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** What this person can do, from their role — the answer to "why can't they
 *  open that page?". */
export function CapabilitiesCard({ user }: { user: AdminUserRecord }) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeader>
        <CardTitle as="h2">What they can do</CardTitle>
        <CardDescription>
          {user.custom_role_name
            ? `From the ${user.custom_role_name} role.`
            : "From their role."}{" "}
          {user.capabilities.length} permission{user.capabilities.length === 1 ? "" : "s"}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          {open ? "Hide the list" : "Show the list"}
        </Button>
        {open ? (
          <ul className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2" aria-label="Permissions">
            {user.capabilities.map((row) => (
              <li key={row.code} className="text-ink">
                {row.label}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
