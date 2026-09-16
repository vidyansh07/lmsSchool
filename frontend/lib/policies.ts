/**
 * Policy management (`/api/v1/policies/`, ERP Phase 3, ADR-04).
 *
 * Reading needs `policy.view`; changing or resetting a key needs
 * `policy.manage`. A critical key (`PolicyEntry.critical`) needs a fresh
 * step-up (`stepUpWithPassword` in `lib/roles.ts`) and, on write, `confirm`
 * naming the key exactly — the same step-up contract the permission matrix
 * already uses for locking a grant.
 *
 * The read shapes never say *how* a value is typed (`apps.policies.schemas`
 * stays server-only, on purpose — D-135): `PolicyEntrySerializer` returns the
 * resolved value and its default, nothing about integer/decimal/choice/
 * weights. `policyFieldKind` below infers the right editor from the value's
 * own shape instead of re-declaring the schema on the client, the same way
 * `lib/labels.ts` already hand-mirrors small backend enumerations rather than
 * fetching them.
 */

import { apiFetch, apiMutate, queryString } from "./api";
import type {
  Paginated,
  PolicyEntry,
  PolicyValue,
  PolicyVersion,
} from "@/types/api";

export async function listPolicies(
  params: { category?: string; branch?: string } = {},
): Promise<PolicyEntry[]> {
  return apiFetch<PolicyEntry[]>(`/api/v1/policies/${queryString(params)}`);
}

export async function getPolicy(
  category: string,
  key: string,
  branch?: string,
): Promise<PolicyEntry> {
  return apiFetch<PolicyEntry>(
    `/api/v1/policies/${category}/${key}/${queryString({ branch })}`,
  );
}

export interface UpdatePolicyPayload {
  value: PolicyValue;
  reason: string;
  branch?: string | null;
  confirm?: string;
}

export async function updatePolicy(
  category: string,
  key: string,
  payload: UpdatePolicyPayload,
): Promise<PolicyEntry> {
  return apiMutate<PolicyEntry>(`/api/v1/policies/${category}/${key}/`, {
    method: "PUT",
    body: payload,
  });
}

export async function resetPolicy(
  category: string,
  key: string,
  branch?: string,
): Promise<PolicyEntry> {
  return apiMutate<PolicyEntry>(
    `/api/v1/policies/${category}/${key}/${queryString({ branch })}`,
    { method: "DELETE" },
  );
}

export async function getPolicyHistory(
  category: string,
  key: string,
  query: { branch?: string; page?: number; page_size?: number } = {},
): Promise<Paginated<PolicyVersion>> {
  return apiFetch<Paginated<PolicyVersion>>(
    `/api/v1/policies/${category}/${key}/history/${queryString(query)}`,
  );
}

// --- Rendering the right editor for a value ---------------------------------

export type PolicyFieldKind =
  "integer" | "decimal" | "boolean" | "choice" | "weights";

/** `notification.digest_frequency`'s only choice key today; a schema key that
 *  gains its own choice list later just adds an entry here. */
export const POLICY_CHOICES: Record<string, string[]> = {
  "notification.digest_frequency": ["immediate", "daily", "weekly"],
};

/** The components `performance.weights` carries, mirroring
 *  `apps.policies.schemas.PERFORMANCE_COMPONENTS`. `activity` (ERP Phase 12,
 *  ADR-10) is the sixth: the backend rejects a `PUT` that does not name
 *  every key here exactly, so this list must stay in lockstep with the
 *  backend tuple, not just add up to the same components by coincidence. */
export const PERFORMANCE_COMPONENTS = [
  "attendance",
  "assessment",
  "assignments",
  "projects",
  "progress",
  "activity",
] as const;

export const PERFORMANCE_COMPONENT_LABEL: Record<
  (typeof PERFORMANCE_COMPONENTS)[number],
  string
> = {
  attendance: "Attendance",
  assessment: "Assessment average",
  assignments: "Assignments",
  projects: "Projects",
  progress: "Progress vs. plan",
  activity: "Activity",
};

/** Which editor a `category.key` needs, from the resolved value's own shape
 *  plus the two hand-mirrored tables above. */
export function policyFieldKind(
  category: string,
  key: string,
  value: PolicyValue,
): PolicyFieldKind {
  if (POLICY_CHOICES[`${category}.${key}`]) return "choice";
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "object") return "weights";
  if (typeof value === "number") return "integer";
  return "decimal";
}

/** A `PolicyValue` as plain text, for the "current"/"default" columns. */
export function formatPolicyValue(value: PolicyValue): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") {
    return PERFORMANCE_COMPONENTS.map(
      (component) =>
        `${PERFORMANCE_COMPONENT_LABEL[component]}: ${value[component] ?? "—"}`,
    ).join(", ");
  }
  return String(value);
}
