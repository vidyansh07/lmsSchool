"use client";

/**
 * The MFA section of the security settings screen (ERP Phase 5, ADR-05):
 * enrol a TOTP device, disable it, or regenerate recovery codes. Sits
 * alongside the password and sessions cards `app/settings/security/page.tsx`
 * already has, following the same "one Card, one concern" shape.
 *
 * `useAuth().user.mfa_enabled` is what decides which half renders; a
 * mutation that changes it (confirm, disable) calls `refresh()` afterwards
 * rather than guessing the new value locally, the same way every other
 * screen in this app treats the signed-in user as server state.
 */

import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  isStepUpRequired,
  StepUpDialog,
} from "@/components/roles/step-up-dialog";
import { RecoveryCodesDialog } from "@/components/settings/recovery-codes-dialog";
import { ErrorState, LoadingState } from "@/components/states";
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
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import {
  confirmTotpEnrolment,
  disableTotp,
  enrolTotp,
  regenerateRecoveryCodes,
} from "@/lib/mfa";
import type { MfaEnrolResponse } from "@/types/api";

type PendingAction = "disable" | "regenerate" | null;

export function MfaSettingsCard() {
  const { user, refresh } = useAuth();
  const mfaEnabled = user?.mfa_enabled ?? false;

  // --- Enrolment dialog: fetch a secret, then confirm a code. -------------
  const [enrolOpen, setEnrolOpen] = useState(false);
  const [enrolment, setEnrolment] = useState<MfaEnrolResponse | null>(null);
  const [isStartingEnrol, setIsStartingEnrol] = useState(false);
  const [enrolError, setEnrolError] = useState<string | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [isConfirming, setIsConfirming] = useState(false);

  // --- The one-time recovery-codes reveal, from confirm or regenerate. ----
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  // --- Disable / regenerate, both gated on a fresh step-up. ----------------
  const [stepUpOpen, setStepUpOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isActing, setIsActing] = useState(false);

  async function openEnrol() {
    setEnrolOpen(true);
    setEnrolment(null);
    setEnrolError(null);
    setConfirmCode("");
    setIsStartingEnrol(true);
    try {
      setEnrolment(await enrolTotp());
    } catch (cause) {
      setEnrolError(
        errorMessage(cause, "Could not start enrolment. Try again."),
      );
    } finally {
      setIsStartingEnrol(false);
    }
  }

  function closeEnrol() {
    setEnrolOpen(false);
    setEnrolment(null);
    setConfirmCode("");
    setEnrolError(null);
  }

  async function confirmEnrol(event: React.FormEvent) {
    event.preventDefault();
    setIsConfirming(true);
    setEnrolError(null);
    try {
      const { recovery_codes } = await confirmTotpEnrolment(confirmCode);
      closeEnrol();
      await refresh();
      setRecoveryCodes(recovery_codes);
    } catch (cause) {
      setEnrolError(
        errorMessage(cause, "That code is not right or has expired."),
      );
    } finally {
      setIsConfirming(false);
    }
  }

  async function runAction(action: PendingAction) {
    if (!action) return;
    setIsActing(true);
    setActionError(null);
    try {
      if (action === "disable") {
        await disableTotp();
        await refresh();
        setPendingAction(null);
      } else {
        const { recovery_codes } = await regenerateRecoveryCodes();
        setPendingAction(null);
        setRecoveryCodes(recovery_codes);
      }
    } catch (cause) {
      if (isStepUpRequired(cause)) {
        setPendingAction(action);
        setStepUpOpen(true);
      } else {
        setActionError(errorMessage(cause, "That could not be completed."));
        setPendingAction(null);
      }
    } finally {
      setIsActing(false);
    }
  }

  const canConfirm = confirmCode.length === 6;

  return (
    <Card className="">
      <CardHeader>
        <CardTitle>Two-factor authentication</CardTitle>
        <CardDescription>
          {mfaEnabled
            ? "An authenticator app is protecting your account."
            : "Add a second step to sign-in with an authenticator app."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {actionError ? <Alert variant="error">{actionError}</Alert> : null}
        {mfaEnabled ? (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void runAction("regenerate")}
              disabled={isActing}
            >
              Regenerate recovery codes
            </Button>
            <Button
              variant="destructive"
              onClick={() => void runAction("disable")}
              disabled={isActing}
            >
              Disable two-factor authentication
            </Button>
          </div>
        ) : (
          <Button onClick={() => void openEnrol()}>
            Set up authenticator app
          </Button>
        )}
      </CardContent>

      <Dialog
        open={enrolOpen}
        onOpenChange={(next) => (next ? undefined : closeEnrol())}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Set up two-factor authentication</DialogTitle>
            <DialogDescription>
              Scan this with your authenticator app, then enter the 6-digit code
              it shows.
            </DialogDescription>
          </DialogHeader>
          {isStartingEnrol ? (
            <LoadingState label="Preparing your authenticator…" rows={3} />
          ) : enrolment ? (
            <form onSubmit={confirmEnrol} className="space-y-4">
              {enrolError ? <Alert variant="error">{enrolError}</Alert> : null}
              <div
                className="mx-auto w-40 max-w-full [&_svg]:h-auto [&_svg]:w-full"
                // Server-rendered SVG (`apps.accounts.mfa.qr_svg`): a QR code
                // encoding the provisioning URI, never anything user-supplied
                // — the one place this app renders markup it did not build.
                dangerouslySetInnerHTML={{ __html: enrolment.qr_svg }}
              />
              <Field
                label="Can't scan? Enter this key manually"
                htmlFor="mfa-secret"
              >
                <Input
                  id="mfa-secret"
                  readOnly
                  value={enrolment.secret}
                  onFocus={(event) => event.target.select()}
                />
              </Field>
              <Field label="Code from your app" htmlFor="mfa-confirm-code">
                <Input
                  id="mfa-confirm-code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  autoFocus
                  value={confirmCode}
                  onChange={(event) =>
                    setConfirmCode(
                      event.target.value.replace(/\D/g, "").slice(0, 6),
                    )
                  }
                />
              </Field>
              <DialogFooter>
                <Button type="button" variant="ghost" onClick={closeEnrol}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isConfirming || !canConfirm}>
                  {isConfirming ? "Confirming…" : "Turn on"}
                </Button>
              </DialogFooter>
            </form>
          ) : (
            <ErrorState
              message={enrolError ?? "Could not start enrolment."}
              onRetry={() => void openEnrol()}
            />
          )}
        </DialogContent>
      </Dialog>

      <RecoveryCodesDialog
        codes={recoveryCodes}
        onDismiss={() => setRecoveryCodes(null)}
      />

      <StepUpDialog
        open={stepUpOpen}
        onConfirmed={() => {
          setStepUpOpen(false);
          void runAction(pendingAction);
        }}
        onCancel={() => {
          setStepUpOpen(false);
          setPendingAction(null);
        }}
      />
    </Card>
  );
}
