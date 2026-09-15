"use client";

/**
 * The sessions section of the admin user page (ERP Phase 6, ADR-06).
 *
 * Shown only to a caller holding `session.view_any` — gated the same way
 * `ScopeGrantsCard` is on `app/admin/users/[userId]/page.tsx` — and ending a
 * session additionally requires `session.revoke_any` plus a fresh step-up.
 * There is no separate "are you sure" step here: clicking "Revoke" attempts
 * the revoke directly, exactly like `MfaSettingsCard`'s "Disable two-factor
 * authentication" does, and a `403 step_up_required` refusal is what opens
 * {@link StepUpDialog} — the step-up itself is the confirmation. Success
 * retries the same revoke once.
 *
 * `is_current` is meaningless on this listing (it would compare against the
 * *admin's own* session, not the row it sits beside), so `SessionList` is
 * told not to render it.
 */

import { useCallback, useEffect, useState } from "react";

import {
  isStepUpRequired,
  StepUpDialog,
} from "@/components/roles/step-up-dialog";
import { SessionList } from "@/components/settings/session-list";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { errorMessage } from "@/lib/api";
import { listUserSessions, revokeUserSession } from "@/lib/sessions";
import type { SessionRow } from "@/types/api";

export function UserSessionsCard({ userId }: { userId: string }) {
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [target, setTarget] = useState<SessionRow | null>(null);
  const [isRevoking, setIsRevoking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [stepUpOpen, setStepUpOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    listUserSessions(userId)
      .then((rows) => {
        setSessions(rows);
        setLoadError(null);
      })
      .catch((cause) =>
        setLoadError(
          errorMessage(cause, "Could not load this account's sessions."),
        ),
      );
  }, [userId]);

  useEffect(load, [load]);

  async function attemptRevoke(row: SessionRow) {
    setTarget(row);
    setIsRevoking(true);
    setActionError(null);
    try {
      await revokeUserSession(userId, row.id);
      setNotice(`Signed "${row.device_label}" out.`);
      setTarget(null);
      load();
    } catch (cause) {
      if (isStepUpRequired(cause)) {
        setStepUpOpen(true);
      } else {
        setActionError(
          errorMessage(cause, "That session could not be revoked."),
        );
        setTarget(null);
      }
    } finally {
      setIsRevoking(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sessions</CardTitle>
        <CardDescription>
          Every device this account is currently signed in on. Ending one
          signs it out immediately and emails them a notice.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {notice ? <Alert variant="success">{notice}</Alert> : null}
        {actionError ? <Alert variant="error">{actionError}</Alert> : null}
        {loadError ? (
          <ErrorState message={loadError} onRetry={load} />
        ) : sessions === null ? (
          <LoadingState label="Loading sessions…" rows={3} />
        ) : sessions.length === 0 ? (
          <EmptyState
            title="No active sessions"
            description="This account is not currently signed in anywhere."
          />
        ) : (
          <SessionList
            sessions={sessions}
            showCurrentBadge={false}
            revokingId={isRevoking ? (target?.id ?? null) : null}
            onRevoke={(row) => {
              setNotice(null);
              setActionError(null);
              void attemptRevoke(row);
            }}
          />
        )}
      </CardContent>

      <StepUpDialog
        open={stepUpOpen}
        onConfirmed={() => {
          setStepUpOpen(false);
          if (target) void attemptRevoke(target);
        }}
        onCancel={() => {
          setStepUpOpen(false);
          setTarget(null);
        }}
      />
    </Card>
  );
}
