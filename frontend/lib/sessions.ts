/**
 * Session inventory and revocation (`/api/v1/auth/sessions/…` and
 * `/api/v1/users/{id}/sessions/…`, ERP Phase 6, ADR-06).
 *
 * The server is the only place that ever sees a session key or its hash —
 * every shape here carries an opaque `id` and a human `device_label`, never
 * anything that could be replayed. `revokeSession`/`revokeUserSession` may
 * fail `409 current_session` (the caller named their own current session;
 * point them at `logoutEverywhere`/`logout` instead) or `403
 * step_up_required` (the admin path only), which callers surface with
 * {@link isStepUpRequired} exactly as `lib/mfa.ts` does.
 */

import { apiFetch, apiMutate } from "./api";
import type { DetailResponse, SessionRow } from "@/types/api";

/** The caller's own non-revoked sessions, newest activity first. */
export async function listSessions(): Promise<SessionRow[]> {
  return apiFetch<SessionRow[]>("/api/v1/auth/sessions/");
}

/** Revoke one of the caller's own sessions. `404` if it is not one of theirs
 *  (or already revoked); `409 current_session` if it is the very session
 *  making this request — `logoutEverywhere`/logout is the right call there. */
export async function revokeSession(id: string): Promise<void> {
  await apiMutate<void>(`/api/v1/auth/sessions/${id}/`, { method: "DELETE" });
}

/** Sign out of every one of the caller's sessions except the current one. */
export async function revokeOtherSessions(): Promise<DetailResponse> {
  return apiMutate<DetailResponse>("/api/v1/auth/sessions/revoke-others/", {
    method: "POST",
  });
}

/** An administrator's view of somebody else's active sessions. Requires
 *  `session.view_any`; `user_id` is resolved through the caller's own
 *  visible-accounts scope, so a cross-centre id 404s. */
export async function listUserSessions(userId: string): Promise<SessionRow[]> {
  return apiFetch<SessionRow[]>(`/api/v1/users/${userId}/sessions/`);
}

/** An administrator ending somebody else's session. Requires
 *  `session.revoke_any` plus a fresh step-up — a `403 step_up_required`
 *  refusal is the caller's cue to open {@link StepUpDialog} and retry. */
export async function revokeUserSession(
  userId: string,
  sessionId: string,
): Promise<void> {
  await apiMutate<void>(`/api/v1/users/${userId}/sessions/${sessionId}/`, {
    method: "DELETE",
  });
}
