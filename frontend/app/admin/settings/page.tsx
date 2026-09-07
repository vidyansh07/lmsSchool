'use client';

import { useEffect, useId, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { formatDateTime, UNKNOWN } from '@/lib/format';
import {
  getSettings,
  updateSettings,
  type SystemSettings,
  type SystemSettingsPatch,
} from '@/lib/settings';

/** Every value the form edits, held as the strings the inputs actually carry. */
interface FormState {
  institution_name: string;
  support_email: string;
  support_phone: string;
  notification_email_enabled: string;
  export_retention_days: string;
  resource_upload_max_mb: string;
}

function toForm(row: SystemSettings): FormState {
  return {
    institution_name: row.institution_name,
    support_email: row.support_email,
    support_phone: row.support_phone,
    notification_email_enabled: String(row.notification_email_enabled),
    export_retention_days: String(row.export_retention_days),
    resource_upload_max_mb: String(row.resource_upload_max_mb),
  };
}

/**
 * Only what the operator actually moved.
 *
 * The backend audits the *names* of the fields that changed, so sending the
 * whole form back would record "they changed everything" every time somebody
 * corrected a typo in a phone number.
 */
function changedFields(form: FormState, original: FormState): SystemSettingsPatch {
  const patch: SystemSettingsPatch = {};
  if (form.institution_name !== original.institution_name) {
    patch.institution_name = form.institution_name;
  }
  if (form.support_email !== original.support_email) patch.support_email = form.support_email;
  if (form.support_phone !== original.support_phone) patch.support_phone = form.support_phone;
  if (form.notification_email_enabled !== original.notification_email_enabled) {
    patch.notification_email_enabled = form.notification_email_enabled === 'true';
  }
  if (form.export_retention_days !== original.export_retention_days) {
    patch.export_retention_days = Number(form.export_retention_days);
  }
  if (form.resource_upload_max_mb !== original.resource_upload_max_mb) {
    patch.resource_upload_max_mb = Number(form.resource_upload_max_mb);
  }
  return patch;
}

/** What the load produced, and which attempt produced it. */
interface LoadState {
  form: FormState | null;
  original: FormState | null;
  /** Kept alongside the form because provenance is not something the operator
   *  edits, and folding it into `FormState` would make it look editable. */
  row: SystemSettings | null;
  error: ApiError | null;
  isLoading: boolean;
  attempt: number;
}

function InstitutionSettings() {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>({
    form: null,
    original: null,
    row: null,
    error: null,
    isLoading: true,
    attempt,
  });

  // Adjusted during render rather than from inside the effect: a synchronous
  // `setState` at the top of an effect body causes a cascading render, and the
  // lint config rejects it. `use-api.ts` does the same, for the same reason.
  if (state.attempt !== attempt) {
    setState({ form: null, original: null, row: null, error: null, isLoading: true, attempt });
  }

  // Generated, never literal: two controls sharing a hardcoded id on one page
  // collide silently, and a label stops pointing at its own input.
  const nameId = useId();
  const emailId = useId();
  const phoneId = useId();
  const mailSwitchId = useId();
  const retentionId = useId();
  const uploadId = useId();

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((row) => {
        if (cancelled) return;
        setState({
          form: toForm(row),
          original: toForm(row),
          row,
          error: null,
          isLoading: false,
          attempt,
        });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setState({
          form: null,
          original: null,
          row: null,
          error: cause instanceof ApiError ? cause : null,
          isLoading: false,
          attempt,
        });
      });
    // Stops a stale response overwriting a newer one after a retry.
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const { form, original, row, error, isLoading } = state;

  function edit(change: Partial<FormState>) {
    setState((current) =>
      current.form ? { ...current, form: { ...current.form, ...change } } : current,
    );
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!form || !original) return;
    setIsSaving(true);
    setErrors({});
    setNotice(null);
    try {
      const saved = await updateSettings(changedFields(form, original));
      setState((current) => ({
        ...current,
        form: toForm(saved),
        original: toForm(saved),
        row: saved,
      }));
      setNotice('Settings saved. They apply from the next request.');
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading the institution's settings…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the institution's settings"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={() => setAttempt((value) => value + 1)}
      />
    );
  }
  if (!form) return null;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Institution settings</h1>
        <p className="text-sm text-muted-foreground">
          Who this institution is to the people it writes to, and the operational limits an
          administrator changes without a deployment.
        </p>
      </div>

      {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

      <Card>
        <CardHeader>
          <CardTitle>Identity and contact</CardTitle>
          <CardDescription>
            The name signs off every email this system sends. The contact details appear there too,
            and on the profile screen every signed-in person can open.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" noValidate onSubmit={save}>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Institution name" htmlFor={nameId} error={errors.institution_name}>
                <Input
                  value={form.institution_name}
                  onChange={(event) => edit({ institution_name: event.target.value })}
                />
              </Field>

              <Field label="Support email" htmlFor={emailId} error={errors.support_email}>
                <Input
                  type="email"
                  value={form.support_email}
                  onChange={(event) => edit({ support_email: event.target.value })}
                />
              </Field>

              <Field label="Support phone" htmlFor={phoneId} error={errors.support_phone}>
                <Input
                  type="tel"
                  value={form.support_phone}
                  onChange={(event) => edit({ support_phone: event.target.value })}
                />
              </Field>

              <Field
                label="Send notification email"
                htmlFor={mailSwitchId}
                error={errors.notification_email_enabled}
                hint="Turning this off suppresses delivery only. Notifications are still written."
              >
                <Select
                  value={form.notification_email_enabled}
                  onChange={(event) => edit({ notification_email_enabled: event.target.value })}
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </Select>
              </Field>

              <Field
                label="Keep exports for (days)"
                htmlFor={retentionId}
                error={errors.export_retention_days}
                hint="Between 1 and 365."
              >
                <Input
                  type="number"
                  min="1"
                  max="365"
                  step="1"
                  value={form.export_retention_days}
                  onChange={(event) => edit({ export_retention_days: event.target.value })}
                />
              </Field>

              <Field
                label="Largest upload (MB)"
                htmlFor={uploadId}
                error={errors.resource_upload_max_mb}
                hint="Between 1 and 100. Applies to course resources and assignment attachments."
              >
                <Input
                  type="number"
                  min="1"
                  max="100"
                  step="1"
                  value={form.resource_upload_max_mb}
                  onChange={(event) => edit({ resource_upload_max_mb: event.target.value })}
                />
              </Field>
            </div>

            <div className="flex gap-2">
              <Button type="submit" disabled={isSaving}>
                {isSaving ? 'Saving…' : 'Save settings'}
              </Button>
            </div>

            {notice ? (
              <Alert variant="success" role="status">
                {notice}
              </Alert>
            ) : null}

            {/* Absent, rather than "Not available", until somebody has saved
                once: on a fresh install nobody has changed anything, and a
                line saying so would only invite the question. */}
            {row?.updated_at ? (
              <p className="text-xs text-muted-foreground">
                Last changed by {row.updated_by_name || UNKNOWN} on{' '}
                {formatDateTime(row.updated_at)}.
              </p>
            ) : null}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default function InstitutionSettingsPage() {
  return (
    <RequireAuth capability={Capability.settingsManage}>
      <InstitutionSettings />
    </RequireAuth>
  );
}
