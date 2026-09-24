"use client";

/**
 * The sessions section of the security settings screen (ERP Phase 6,
 * ADR-06): every device with an active session, a per-device "Revoke", and
 * "sign out everywhere else" — plus the existing "sign out everywhere"
 * (this device included), which is `POST /auth/logout-all/` and, unlike the
 * other two actions here, ends the caller's own browsing session, so it
 * redirects to `/login` afterwards exactly as it always has.
 *
 * The current session never gets a revoke control (`SessionList` renders an
 * explanation instead) — revoking the session making the very request that
 * revokes it is a contradiction the server also refuses (`409
 * current_session`); this screen just never offers the button in the first
 * place.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { SessionList } from "@/components/settings/session-list";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
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
import { ApiError, errorMessage } from "@/lib/api";
import { logoutEverywhere } from "@/lib/auth";
import { listSessions, revokeOtherSessions, revokeSession } from "@/lib/sessions";
import type { SessionRow } from "@/types/api";

export function SessionsCard() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [revoking, setRevoking] = useState<SessionRow | null>(null);
  const [isRevoking, setIsRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const [isRevokingOthers, setIsRevokingOthers] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [isRevokingAll, setIsRevokingAll] = useState(false);
  const [revokeAllMessage, setRevokeAllMessage] = useState<string | null>(
    null,
  );

  const load = useCallback(() => {
    listSessions()
      .then((rows) => {
        setSessions(rows);
        setLoadError(null);
      })
      .catch((cause) =>
        setLoadError(errorMessage(cause, "Could not load your sessions.")),
      );
  }, []);

  useEffect(load, [load]);

  async function confirmRevoke() {
    if (!revoking) return;
    setIsRevoking(true);
    setRevokeError(null);
    try {
      await revokeSession(revoking.id);
      setRevoking(null);
      load();
    } catch (cause) {
      setRevokeError(
        errorMessage(cause, "That session could not be revoked."),
      );
    } finally {
      setIsRevoking(false);
    }
  }

  async function onRevokeOthers() {
    setIsRevokingOthers(true);
    setActionError(null);
    setNotice(null);
    try {
      const response = await revokeOtherSessions();
      setNotice(response.detail);
      load();
    } catch (cause) {
      setActionError(
        errorMessage(cause, "Could not sign out of other sessions."),
      );
    } finally {
      setIsRevokingOthers(false);
    }
  }

  async function onRevokeAll() {
    setIsRevokingAll(true);
    try {
      const response = await logoutEverywhere();
      setRevokeAllMessage(response.detail);
      // Signing out everywhere includes this browser, so send the user to the
      // sign-in page rather than leaving a dead session on screen.
      router.replace("/login");
    } catch (cause) {
      setRevokeAllMessage(
        cause instanceof ApiError
          ? cause.message
          : "Could not sign out of other sessions.",
      );
    } finally {
      setIsRevokingAll(false);
    }
  }

  const others = sessions?.filter((row) => !row.is_current) ?? [];

  return (
    <Card className="">
      <CardHeader>
        <CardTitle>Active sessions</CardTitle>
        <CardDescription>
          Every device currently signed in to your account. Revoke one you no
          longer use, or sign out of all of them at once.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {actionError ? <Alert variant="error">{actionError}</Alert> : null}
        {notice ? <Alert variant="success">{notice}</Alert> : null}

        {loadError ? (
          <ErrorState message={loadError} onRetry={load} />
        ) : sessions === null ? (
          <LoadingState label="Loading your sessions…" rows={3} />
        ) : sessions.length === 0 ? (
          <EmptyState
            title="No active sessions"
            description="Nothing is showing here right now."
          />
        ) : (
          <>
            <SessionList
              sessions={sessions}
              onRevoke={(row) => {
                setRevokeError(null);
                setRevoking(row);
              }}
            />
            {others.length > 0 ? (
              <Button
                type="button"
                variant="outline"
                disabled={isRevokingOthers}
                onClick={() => void onRevokeOthers()}
              >
                {isRevokingOthers
                  ? "Signing out…"
                  : "Sign out everywhere else"}
              </Button>
            ) : null}
          </>
        )}

        <div className="border-t border-border pt-3">
          {revokeAllMessage ? (
            <Alert variant="info" className="mb-3">
              {revokeAllMessage}
            </Alert>
          ) : null}
          <Button
            variant="destructive"
            disabled={isRevokingAll}
            onClick={() => void onRevokeAll()}
          >
            {isRevokingAll ? "Signing out…" : "Sign out everywhere"}
          </Button>
          <p className="mt-2 text-sm text-muted-foreground">
            Ends every session, including this one. Use this if you think
            someone else has access to your account.
          </p>
        </div>
      </CardContent>

      <Dialog
        open={revoking !== null}
        onOpenChange={(next) =>
          next ? undefined : (setRevoking(null), setRevokeError(null))
        }
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sign out this device?</DialogTitle>
            <DialogDescription>
              {revoking
                ? `"${revoking.device_label}" will be signed out immediately.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          {revokeError ? <Alert variant="error">{revokeError}</Alert> : null}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setRevoking(null);
                setRevokeError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={isRevoking}
              onClick={() => void confirmRevoke()}
            >
              {isRevoking ? "Signing out…" : "Sign out"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
