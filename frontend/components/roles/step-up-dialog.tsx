"use client";

/**
 * The step-up dialog (ADR-05/ADR-03): prove it is still you, right before a
 * dangerous act. Opened by the caller when a request comes back
 * `403 step_up_required`; on success the caller retries the original request
 * once. This component never retries anything itself — it only proves
 * freshness and reports back.
 *
 * Two ways in (Phase 4, ADR-05): re-enter the password (the default), or
 * follow "Send me a code instead" to email a 6-digit one-time code and
 * switch to entering that. Both end at the same `POST .../step-up/`, so the
 * caller sees one success shape regardless of which the person used.
 */

import { useState } from "react";
import { PasswordInput } from '@/components/ui/input';

import { Alert } from "@/components/ui/alert";
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
import { errorMessage, rateLimitMessage } from "@/lib/api";
import {
  requestStepUpCode,
  stepUpWithCode,
  stepUpWithPassword,
} from "@/lib/roles";

type Mode = "password" | "code";

/** Re-exported for `components/auth/mfa-verify-form.tsx`, which imported it
 *  from here before it moved to `lib/api` — where `fieldErrors` now uses it
 *  so every form reports a throttle the same way. */
export { rateLimitMessage };

export function StepUpDialog({
  open,
  onConfirmed,
  onCancel,
}: {
  open: boolean;
  onConfirmed: () => void;
  onCancel: () => void;
}) {
  const [mode, setMode] = useState<Mode>("password");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [isSendingCode, setIsSendingCode] = useState(false);

  // Reopening starts fresh: a code from a previous, cancelled attempt should
  // not linger in the field, and the dialog should not silently reopen mid
  // code-entry for an unrelated action. Adjusted during render (the React-
  // sanctioned way to reset state on a prop change) rather than in an effect,
  // so there is no extra render between "just opened" and "reset".
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setMode("password");
      setPassword("");
      setCode("");
      setError(null);
      setInfo(null);
      setIsChecking(false);
      setIsSendingCode(false);
    }
  }

  async function requestCode() {
    setIsSendingCode(true);
    setError(null);
    setInfo(null);
    try {
      const { detail } = await requestStepUpCode();
      setMode("code");
      setCode("");
      setInfo(detail);
    } catch (cause) {
      setError(
        rateLimitMessage(cause) ??
          errorMessage(cause, "Could not send a code. Try again."),
      );
    } finally {
      setIsSendingCode(false);
    }
  }

  function useCodeInstead() {
    void requestCode();
  }

  function usePasswordInstead() {
    setMode("password");
    setCode("");
    setError(null);
    setInfo(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setIsChecking(true);
    setError(null);
    try {
      if (mode === "password") {
        await stepUpWithPassword(password);
      } else {
        await stepUpWithCode(code);
      }
      setPassword("");
      setCode("");
      onConfirmed();
    } catch (cause) {
      setError(
        mode === "password"
          ? errorMessage(cause, "That password is not right.")
          : errorMessage(cause, "That code is not right or has expired."),
      );
    } finally {
      setIsChecking(false);
    }
  }

  const canSubmit =
    mode === "password" ? password.length > 0 : code.length === 6;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? undefined : onCancel())}
    >
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Confirm it is you</DialogTitle>
            <DialogDescription>
              {mode === "password"
                ? "This action is sensitive. Enter your password to continue."
                : "This action is sensitive. Enter the code we emailed you to continue."}
            </DialogDescription>
          </DialogHeader>
          {error ? <Alert variant="error">{error}</Alert> : null}
          {!error && info ? <Alert variant="info">{info}</Alert> : null}
          {mode === "password" ? (
            <Field label="Password" htmlFor="step-up-password">
              <PasswordInput
                id="step-up-password"
                required
                autoFocus
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
          ) : (
            <Field label="One-time code" htmlFor="step-up-code">
              <Input
                id="step-up-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                required
                autoFocus
                value={code}
                onChange={(event) =>
                  setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                }
              />
            </Field>
          )}
          <div className="text-sm">
            {mode === "password" ? (
              <button
                type="button"
                className="text-action underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                onClick={useCodeInstead}
                disabled={isSendingCode}
              >
                {isSendingCode ? "Sending…" : "Send me a code instead"}
              </button>
            ) : (
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  className="text-action underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={useCodeInstead}
                  disabled={isSendingCode}
                >
                  {isSendingCode ? "Sending…" : "Resend code"}
                </button>
                <button
                  type="button"
                  className="text-ink-muted underline-offset-4 hover:underline"
                  onClick={usePasswordInstead}
                >
                  Use your password instead
                </button>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={isChecking || !canSubmit}>
              {isChecking ? "Checking…" : "Confirm"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** True when the failure is a `step_up_required` refusal from the server. */
export function isStepUpRequired(cause: unknown): boolean {
  return (
    typeof cause === "object" &&
    cause !== null &&
    "code" in cause &&
    (cause as { code?: unknown }).code === "step_up_required"
  );
}
