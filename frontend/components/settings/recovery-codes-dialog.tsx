"use client";

/**
 * The one-time reveal of ten recovery codes (ERP Phase 5, ADR-05).
 *
 * Shown right after confirming TOTP enrolment and right after regenerating
 * codes — the only two moments the API ever returns them. This dialog is,
 * by construction, the only place a recovery code exists on the client:
 * `codes` comes from the caller's own state and `onDismiss` is expected to
 * clear it there. This component holds no copy of its own beyond the
 * `codes` prop it was given — no `localStorage`, no `sessionStorage`, no
 * state that survives a dismiss — so once the caller clears its state there
 * is nothing left anywhere to recover (hard rule §6).
 */

import { useState } from "react";
import { Check, Copy } from "lucide-react";

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

export function RecoveryCodesDialog({
  codes,
  onDismiss,
}: {
  /** `null` when there is nothing to show — the dialog is closed. */
  codes: string[] | null;
  /** Called when the person confirms they have saved the codes. The caller
   *  must clear `codes` in response; this component never does it itself. */
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copyCodes() {
    if (!codes) return;
    try {
      await navigator.clipboard.writeText(codes.join("\n"));
      setCopied(true);
    } catch {
      // No clipboard permission, or no Clipboard API at all (an older
      // browser, or this project's own jsdom test environment without a
      // mock) — the codes are still on screen to copy by hand.
      setCopied(false);
    }
  }

  function dismiss() {
    setCopied(false);
    onDismiss();
  }

  return (
    <Dialog
      open={codes !== null}
      onOpenChange={(next) => (next ? undefined : dismiss())}
    >
      <DialogContent hideCloseButton>
        <DialogHeader>
          <DialogTitle>Save your recovery codes</DialogTitle>
          <DialogDescription>
            Each code works once, to sign in if you lose access to your
            authenticator app. Save them somewhere safe now — you will not be
            able to see them again.
          </DialogDescription>
        </DialogHeader>
        {codes ? (
          <div className="space-y-3">
            <ul className="grid sm:grid-cols-2 gap-x-4 gap-y-2 rounded-md border border-border bg-muted p-3 font-mono text-sm">
              {codes.map((code) => (
                <li key={code}>{code}</li>
              ))}
            </ul>
            <Button
              type="button"
              variant="outline"
              onClick={() => void copyCodes()}
              className="w-full"
            >
              {copied ? (
                <Check className="size-4" aria-hidden="true" />
              ) : (
                <Copy className="size-4" aria-hidden="true" />
              )}
              {copied ? "Copied" : "Copy all codes"}
            </Button>
            <Alert variant="warning">
              Generating a new set later replaces these — the old codes stop
              working the moment new ones are issued.
            </Alert>
          </div>
        ) : null}
        <DialogFooter>
          <Button type="button" onClick={dismiss}>
            I&apos;ve saved these codes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
