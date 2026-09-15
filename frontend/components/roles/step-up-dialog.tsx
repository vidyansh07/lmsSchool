"use client";

/**
 * The step-up dialog (ADR-05/ADR-03): re-enter your password to prove it is
 * still you, right before a dangerous act. Opened by the caller when a
 * request comes back `403 step_up_required`; on success the caller retries
 * the original action once. This component never retries anything itself —
 * it only proves freshness and reports back.
 */

import { useState } from "react";

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
import { errorMessage } from "@/lib/api";
import { stepUpWithPassword } from "@/lib/roles";

export function StepUpDialog({
  open,
  onConfirmed,
  onCancel,
}: {
  open: boolean;
  onConfirmed: () => void;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setIsChecking(true);
    setError(null);
    try {
      await stepUpWithPassword(password);
      setPassword("");
      onConfirmed();
    } catch (cause) {
      setError(errorMessage(cause, "That password is not right."));
    } finally {
      setIsChecking(false);
    }
  }

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
              This action is sensitive. Enter your password to continue.
            </DialogDescription>
          </DialogHeader>
          {error ? <Alert variant="error">{error}</Alert> : null}
          <Field label="Password" htmlFor="step-up-password">
            <Input
              id="step-up-password"
              type="password"
              required
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={isChecking || !password}>
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
