/**
 * Trainer requirements (`/api/v1/requirements/`, D-132): a manager's ask of
 * the teaching staff, the trainers' replies on it, and how it was settled.
 */

import { apiFetch, apiMutate, queryString } from "./api";
import type { ListQuery } from "./people";
import type {
  Paginated,
  RequirementReply,
  TrainerRequirement,
} from "@/types/api";

export async function listRequirements(
  query: ListQuery = {},
  signal?: AbortSignal,
): Promise<Paginated<TrainerRequirement>> {
  return apiFetch<Paginated<TrainerRequirement>>(
    `/api/v1/requirements/${queryString(query)}`,
    { signal },
  );
}

export async function getRequirement(id: string): Promise<TrainerRequirement> {
  return apiFetch<TrainerRequirement>(`/api/v1/requirements/${id}/`);
}

export interface RaiseRequirementPayload {
  title: string;
  details?: string;
  batch?: string | null;
  needed_by?: string | null;
}

export async function raiseRequirement(
  payload: RaiseRequirementPayload,
): Promise<TrainerRequirement> {
  return apiMutate<TrainerRequirement>("/api/v1/requirements/", {
    method: "POST",
    body: payload,
  });
}

export async function replyToRequirement(
  id: string,
  message: string,
): Promise<RequirementReply> {
  return apiMutate<RequirementReply>(`/api/v1/requirements/${id}/replies/`, {
    method: "POST",
    body: { message },
  });
}

export async function closeRequirement(
  id: string,
  payload: { fulfilled_by?: string | null; note?: string },
): Promise<TrainerRequirement> {
  return apiMutate<TrainerRequirement>(`/api/v1/requirements/${id}/close/`, {
    method: "POST",
    body: payload,
  });
}

export async function removeRequirement(
  id: string,
  reason: string,
): Promise<void> {
  await apiMutate<void>(`/api/v1/requirements/${id}/`, {
    method: "DELETE",
    body: { reason },
  });
}
