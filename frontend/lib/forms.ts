/**
 * Dynamic forms / form builder (`/api/v1/forms/`, ERP Phase 8).
 *
 * A `FormDefinition` owns a history of `FormVersion`s; only one version is
 * ever `published` at a time, and a version's fields are only writable while
 * it is `draft` (the server refuses a field write on a published version
 * with 409 — see {@link ApiError}). Publishing is refused (409) when the
 * schema hasn't actually changed since the currently published version.
 */

import { apiFetch, apiMutate } from "./api";
import type {
  FormDefinitionDetail,
  FormDefinitionSummary,
  FormEntity,
  FormFieldInput,
  FormPreviewResult,
  FormVersionDetail,
  PublishedForm,
} from "@/types/api";

export interface FormDefinitionListResponse {
  results: FormDefinitionSummary[];
}

export async function listFormDefinitions(): Promise<FormDefinitionListResponse> {
  return apiFetch<FormDefinitionListResponse>("/api/v1/forms/");
}

export async function createFormDefinition(payload: {
  slug: string;
  name: string;
  entity: FormEntity;
}): Promise<FormDefinitionSummary> {
  return apiMutate<FormDefinitionSummary>("/api/v1/forms/", {
    method: "POST",
    body: payload,
  });
}

export async function getFormDefinition(
  slug: string,
): Promise<FormDefinitionDetail> {
  return apiFetch<FormDefinitionDetail>(`/api/v1/forms/${slug}/`);
}

export async function getFormVersion(
  slug: string,
  number: number,
): Promise<FormVersionDetail> {
  return apiFetch<FormVersionDetail>(
    `/api/v1/forms/${slug}/versions/${number}/`,
  );
}

/** Opens a new draft version, optionally cloning an existing version's
 *  fields (typically the published one). */
export async function createFormVersion(
  slug: string,
  payload?: { cloned_from?: number },
): Promise<FormVersionDetail> {
  return apiMutate<FormVersionDetail>(`/api/v1/forms/${slug}/versions/`, {
    method: "POST",
    body: payload ?? {},
  });
}

/** Full replace of a draft version's field list. 409s if the version is no
 *  longer a draft (published under the caller). */
export async function replaceFormFields(
  slug: string,
  number: number,
  fields: FormFieldInput[],
): Promise<FormVersionDetail> {
  return apiMutate<FormVersionDetail>(
    `/api/v1/forms/${slug}/versions/${number}/fields/`,
    { method: "PUT", body: { fields } },
  );
}

/** Archives the current published version (if any) and publishes this one.
 *  409s with `{detail}` if the schema hasn't changed since. */
export async function publishFormVersion(
  slug: string,
  number: number,
): Promise<FormDefinitionDetail> {
  return apiMutate<FormDefinitionDetail>(
    `/api/v1/forms/${slug}/versions/${number}/publish/`,
    { method: "POST", body: {} },
  );
}

export async function unpublishFormVersion(
  slug: string,
  number: number,
): Promise<FormDefinitionDetail> {
  return apiMutate<FormDefinitionDetail>(
    `/api/v1/forms/${slug}/versions/${number}/unpublish/`,
    { method: "POST", body: {} },
  );
}

/** Validates a sample response against the definition's current draft
 *  version without storing anything (the contract takes only `slug` and
 *  `values`, no version — see API_CONTRACTS.md "Forms (Phase 8)"). A
 *  failing preview is a `400 ApiError` whose `.details` carries
 *  `{field: [message, ...]}` — read it with `fieldErrors()` from `./api`. A
 *  successful preview answers `200 {errors: {}}`. */
export async function previewForm(
  slug: string,
  values: Record<string, unknown>,
): Promise<FormPreviewResult> {
  return apiMutate<FormPreviewResult>(`/api/v1/forms/${slug}/preview/`, {
    method: "POST",
    body: { values },
  });
}

/** The published version's fields, for any authenticated user who may
 *  create the owning entity — used by the registration wizard, Student 360,
 *  and the read-only field renderer generally. */
export async function getPublishedForm(slug: string): Promise<PublishedForm> {
  return apiFetch<PublishedForm>(`/api/v1/forms/published/${slug}/`);
}

/** A URL-safe slug from a name, matching the pattern the roles/branches
 *  builders already use. */
export function slugifyFormKey(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}
