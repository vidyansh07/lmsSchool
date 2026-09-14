/**
 * The institution's own settings — `apps/configuration` on the backend.
 *
 * The shapes are declared here rather than in `types/api.ts` for the reason
 * `lib/manage.ts` gives for doing the same: nothing here is a second copy of
 * something `types/api.ts` already describes, so putting it there would spread
 * one feature's contract across two files.
 */

import { apiFetch, apiMutate } from './api';

/**
 * Every setting, as the administrator's form reads them.
 *
 * These are the values in force, not the stored row: the backend resolves an
 * unset column to its code default before answering, so the form and the
 * profile card can never show two different institution names.
 */
export interface SystemSettings {
  institution_name: string;
  support_email: string;
  support_phone: string;
  notification_email_enabled: boolean;
  export_retention_days: number;
  resource_upload_max_mb: number;
  /** Provenance, not settings. Both are null until somebody has saved once. */
  updated_by_name: string | null;
  updated_at: string | null;
}

/**
 * A partial change. The caller sends only what actually moved, which is what
 * makes the audit trail's `context.fields` a record of the change rather than a
 * record that somebody opened the form.
 */
export type SystemSettingsPatch = Partial<
  Pick<
    SystemSettings,
    | 'institution_name'
    | 'support_email'
    | 'support_phone'
    | 'notification_email_enabled'
    | 'export_retention_days'
    | 'resource_upload_max_mb'
  >
>;

/** What anybody signed in may read: who the institution is, and where to write. */
export interface PublicSettings {
  institution_name: string;
  support_email: string;
  support_phone: string;
}

export async function getSettings(): Promise<SystemSettings> {
  return apiFetch<SystemSettings>('/api/v1/settings/');
}

/** Through `apiMutate`, so the CSRF handshake and its one retry cannot be
 *  forgotten. A PATCH is idempotent, so that retry is safe. */
export async function updateSettings(patch: SystemSettingsPatch): Promise<SystemSettings> {
  return apiMutate<SystemSettings>('/api/v1/settings/', { method: 'PATCH', body: patch });
}
