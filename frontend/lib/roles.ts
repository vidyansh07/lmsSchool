/**
 * Roles and the permission catalog (`/api/v1/roles/`, `/api/v1/permissions/`).
 *
 * The catalog is code on the server (ADR-01); what an administrator changes
 * here is which role holds which permission. Every write is a deliberate
 * button, never a side effect of opening a screen.
 */

import { apiFetch, apiMutate } from "./api";
import type {
  PermissionDef,
  PermissionScope,
  Role,
  RoleMatrix,
  RoleSummary,
  UserRole,
} from "@/types/api";

export interface GrantInput {
  code: string;
  scope?: PermissionScope | "";
}

export async function listRoles(): Promise<RoleSummary[]> {
  return apiFetch<RoleSummary[]>("/api/v1/roles/");
}

export async function getRole(slug: string): Promise<Role> {
  return apiFetch<Role>(`/api/v1/roles/${slug}/`);
}

export async function listPermissions(): Promise<PermissionDef[]> {
  return apiFetch<PermissionDef[]>("/api/v1/permissions/");
}

export async function getRoleMatrix(): Promise<RoleMatrix> {
  return apiFetch<RoleMatrix>("/api/v1/roles/matrix/");
}

export async function createRole(payload: {
  slug: string;
  name: string;
  kind: UserRole;
  description?: string;
  permissions: GrantInput[];
}): Promise<Role> {
  return apiMutate<Role>("/api/v1/roles/", { method: "POST", body: payload });
}

export async function updateRole(
  slug: string,
  changes: Partial<{
    name: string;
    description: string;
    status: "active" | "disabled";
    permissions: GrantInput[];
  }>,
): Promise<Role> {
  return apiMutate<Role>(`/api/v1/roles/${slug}/`, {
    method: "PATCH",
    body: changes,
  });
}

export async function deleteRole(slug: string, reason: string): Promise<void> {
  await apiMutate<void>(`/api/v1/roles/${slug}/`, {
    method: "DELETE",
    body: { reason },
  });
}

/** The widest scope a role kind may be configured to (ADR-02). */
export const SCOPE_FLOOR: Record<UserRole, PermissionScope> = {
  superadmin: "all",
  admin: "all",
  manager: "branch",
  counsellor: "branch",
  trainer: "assigned",
  student: "own",
};

const SCOPE_ORDER: PermissionScope[] = ["all", "branch", "assigned", "own"];

/** The scopes a grant on this kind may take, narrowest last. */
export function scopesFor(kind: UserRole): PermissionScope[] {
  return SCOPE_ORDER.slice(SCOPE_ORDER.indexOf(SCOPE_FLOOR[kind]));
}

/** A URL-safe slug from a name, the way the server expects it. */
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

// --- Scopes and locking (ERP Phase 2, ADR-02/ADR-03) ------------------------

export interface ScopeGrantRow {
  id: string;
  batch: string | null;
  batch_code: string | null;
  batch_name: string | null;
  course: string | null;
  course_code: string | null;
  course_title: string | null;
  created_at: string;
}

export async function listScopeGrants(
  userId: string,
): Promise<ScopeGrantRow[]> {
  return apiFetch<ScopeGrantRow[]>(`/api/v1/users/${userId}/scope-grants/`);
}

export async function grantScope(
  userId: string,
  payload: { batch?: string; course?: string },
): Promise<ScopeGrantRow> {
  return apiMutate<ScopeGrantRow>(`/api/v1/users/${userId}/scope-grants/`, {
    method: "POST",
    body: payload,
  });
}

export async function revokeScope(
  userId: string,
  grantId: string,
): Promise<void> {
  await apiMutate<void>(`/api/v1/users/${userId}/scope-grants/${grantId}/`, {
    method: "DELETE",
  });
}

/** Step-up authentication (ADR-05/ADR-03): re-enter the password to unlock a
 *  fresh window for a dangerous action. */
export async function stepUpWithPassword(password: string): Promise<void> {
  await apiMutate<void>("/api/v1/auth/step-up/", {
    method: "POST",
    body: { password },
  });
}

export async function lockPermission(
  roleSlug: string,
  code: string,
): Promise<void> {
  await apiMutate<void>(`/api/v1/roles/${roleSlug}/permissions/${code}/lock/`, {
    method: "POST",
    body: {},
  });
}

export async function unlockPermission(
  roleSlug: string,
  code: string,
): Promise<void> {
  await apiMutate<void>(
    `/api/v1/roles/${roleSlug}/permissions/${code}/unlock/`,
    {
      method: "POST",
      body: {},
    },
  );
}
