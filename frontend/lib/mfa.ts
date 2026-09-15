/**
 * Multi-factor authentication (`/api/v1/auth/mfa/…`, ERP Phase 5, ADR-05).
 *
 * Two contexts share `send-email-code/` and `verify/`: completing a pending
 * sign-in (the session holds `mfa_pending`; `request.user` is anonymous) or,
 * for an already signed-in caller, obtaining step-up. The server tells the
 * two apart on its own (`_resolve_mfa_target`); this module never has to.
 *
 * The TOTP secret and the recovery codes exist in this module's return
 * values for exactly one call each (enrol / confirm and regenerate) and are
 * never written anywhere that outlives that response — no `localStorage`, no
 * component state that survives the reveal dialog. See
 * `components/settings/mfa-recovery-codes-dialog.tsx`.
 */

import { apiMutate } from "./api";
import type {
  CurrentUser,
  MfaEnrolResponse,
  MfaMethodName,
  RecoveryCodesResponse,
} from "@/types/api";

/** Email a one-time code (ADR-05) — against a pending sign-in or, for an
 *  already-authenticated caller, for step-up/enrolment. Throttled. */
export async function sendMfaEmailCode(): Promise<void> {
  await apiMutate<void>("/api/v1/auth/mfa/send-email-code/", {
    method: "POST",
    body: {},
  });
}

/**
 * Complete a pending sign-in, or obtain step-up, with one of the three MFA
 * factors. On success the response is the same {@link CurrentUser} shape an
 * ordinary login returns — the caller passes it straight to
 * `auth-provider`'s `setUser`, exactly like `lib/auth.ts#login`.
 */
export async function verifyMfa(
  method: MfaMethodName,
  code: string,
): Promise<CurrentUser> {
  return apiMutate<CurrentUser>("/api/v1/auth/mfa/verify/", {
    method: "POST",
    body: { method, code },
  });
}

/** Begin (or restart) TOTP enrolment. Returns the raw secret, its
 *  provisioning URI, and a QR code as inline SVG — the only response that
 *  ever carries the secret. Fails `409` if a device is already confirmed. */
export async function enrolTotp(): Promise<MfaEnrolResponse> {
  return apiMutate<MfaEnrolResponse>("/api/v1/auth/mfa/totp/enrol/", {
    method: "POST",
    body: {},
  });
}

/** Confirm TOTP enrolment with a code from the app. On success the device
 *  is active and ten recovery codes come back — shown exactly once. */
export async function confirmTotpEnrolment(
  code: string,
): Promise<RecoveryCodesResponse> {
  return apiMutate<RecoveryCodesResponse>("/api/v1/auth/mfa/totp/confirm/", {
    method: "POST",
    body: { code },
  });
}

/** Turn MFA off. Requires a fresh step-up — a `403 step_up_required` refusal
 *  is the caller's cue to open {@link StepUpDialog} and retry. */
export async function disableTotp(): Promise<void> {
  await apiMutate<void>("/api/v1/auth/mfa/totp/disable/", {
    method: "POST",
    body: {},
  });
}

/** Invalidate every existing recovery code and issue ten new ones, shown
 *  exactly once. Requires a fresh step-up, same as {@link disableTotp}. */
export async function regenerateRecoveryCodes(): Promise<RecoveryCodesResponse> {
  return apiMutate<RecoveryCodesResponse>(
    "/api/v1/auth/mfa/recovery/regenerate/",
    { method: "POST", body: {} },
  );
}
