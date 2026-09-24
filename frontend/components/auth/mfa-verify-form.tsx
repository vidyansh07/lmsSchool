"use client";

/**
 * The MFA-verify step of sign-in (ERP Phase 5, ADR-05).
 *
 * `LoginPage` renders this in place of the credentials form once
 * `POST /auth/login/` answers `{mfa_required: true, methods: [...]}` — the
 * session is already marked pending server-side (`mfa_pending`), so this
 * component's only job is to collect one of the three factors and call
 * `POST /auth/mfa/verify/`. A tab per method the server actually offered
 * (never a method the account cannot use — email is always present, `totp`
 * only with a confirmed device, `recovery` only while unused codes remain).
 *
 * On success the response is the same `CurrentUser` shape an ordinary login
 * returns, so the caller finishes sign-in exactly the way `LoginPage` always
 * has: `setUser` then navigate. Nothing here reimplements that.
 */

import { useState } from "react";

import { rateLimitMessage } from "@/components/roles/step-up-dialog";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { errorMessage } from "@/lib/api";
import { MFA_METHOD_LABEL } from "@/lib/labels";
import { sendMfaEmailCode, verifyMfa } from "@/lib/mfa";
import type { CurrentUser, MfaMethodName } from "@/types/api";

/** Longest code any method accepts, so digits/characters typed past it are
 *  dropped as they are typed rather than rejected only on submit. */
const CODE_MAX_LENGTH: Record<MfaMethodName, number> = {
  totp: 6,
  email: 6,
  recovery: 11, // "XXXXX-XXXXX"
};

const CODE_LABEL: Record<MfaMethodName, string> = {
  totp: "Code from your authenticator app",
  email: "One-time code",
  recovery: "Recovery code",
};

function sanitizeCode(method: MfaMethodName, raw: string): string {
  const cleaned =
    method === "recovery"
      ? raw.toUpperCase().replace(/[^A-Z0-9-]/g, "")
      : raw.replace(/\D/g, "");
  return cleaned.slice(0, CODE_MAX_LENGTH[method]);
}

export function MfaVerifyForm({
  methods,
  onVerified,
  onBack,
}: {
  /** The methods `POST /auth/login/` named — always at least one. */
  methods: MfaMethodName[];
  onVerified: (user: CurrentUser) => void;
  /** "This isn't me" / back to the credentials form. Does not clear the
   *  server's pending state — an unrelated login attempt simply replaces it. */
  onBack: () => void;
}) {
  const [method, setMethod] = useState<MfaMethodName>(methods[0] ?? "email");
  const [code, setCode] = useState("");
  const [emailSent, setEmailSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);

  function selectMethod(next: MfaMethodName) {
    setMethod(next);
    setCode("");
    setEmailSent(false);
    setError(null);
    setInfo(null);
  }

  async function sendCode() {
    setIsSendingCode(true);
    setError(null);
    setInfo(null);
    try {
      await sendMfaEmailCode();
      setEmailSent(true);
      setInfo("A one-time code has been sent to your email.");
    } catch (cause) {
      setError(
        rateLimitMessage(cause) ??
          errorMessage(cause, "Could not send a code. Try again."),
      );
    } finally {
      setIsSendingCode(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setIsVerifying(true);
    setError(null);
    try {
      const user = await verifyMfa(method, code);
      onVerified(user);
    } catch (cause) {
      setError(
        rateLimitMessage(cause) ??
          errorMessage(cause, "That code is not right or has expired."),
      );
    } finally {
      setIsVerifying(false);
    }
  }

  const needsCodeRequest = method === "email" && !emailSent;
  const minLength = method === "recovery" ? 10 : CODE_MAX_LENGTH[method];
  const canSubmit = !needsCodeRequest && code.length >= minLength;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <h2 className="text-xl font-semibold tracking-tight">
          Verify it&apos;s you
        </h2>
        <p className="text-sm text-ink-muted">
          Your account needs a second step to finish signing in.
        </p>
      </div>

      {methods.length > 1 ? (
        <Tabs
          value={method}
          onValueChange={(value) => selectMethod(value as MfaMethodName)}
        >
          <TabsList>
            {methods.map((candidate) => (
              <TabsTrigger key={candidate} value={candidate}>
                {MFA_METHOD_LABEL[candidate]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      ) : null}

      <form onSubmit={submit} className="space-y-4" noValidate>
        {error ? <Alert variant="error">{error}</Alert> : null}
        {!error && info ? <Alert variant="info">{info}</Alert> : null}

        {needsCodeRequest ? (
          <Button
            type="button"
            onClick={() => void sendCode()}
            disabled={isSendingCode}
          >
            {isSendingCode ? "Sending…" : "Send code"}
          </Button>
        ) : (
          <>
            <Field label={CODE_LABEL[method]} htmlFor="mfa-code">
              <Input
                id="mfa-code"
                type="text"
                inputMode={method === "recovery" ? "text" : "numeric"}
                autoComplete="one-time-code"
                maxLength={CODE_MAX_LENGTH[method]}
                autoFocus
                value={code}
                onChange={(event) =>
                  setCode(sanitizeCode(method, event.target.value))
                }
              />
            </Field>
            {method === "email" ? (
              <button
                type="button"
                className="text-sm text-action underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => void sendCode()}
                disabled={isSendingCode}
              >
                {isSendingCode ? "Sending…" : "Resend code"}
              </button>
            ) : null}
          </>
        )}

        <div className="flex items-center justify-between gap-3 pt-1">
          <button
            type="button"
            className="text-sm text-ink-muted underline-offset-4 hover:underline"
            onClick={onBack}
          >
            Back to sign in
          </button>
          <Button type="submit" disabled={isVerifying || !canSubmit}>
            {isVerifying ? "Verifying…" : "Verify"}
          </Button>
        </div>
      </form>
    </div>
  );
}
