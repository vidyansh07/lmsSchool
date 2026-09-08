'use client';

import { useEffect, useState } from 'react';

import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import { getOwnStudentProfile, updateOwnStudentProfile } from '@/lib/people';
import { FEE_STATUS_LABEL, FEE_STATUS_VARIANT, QUALIFICATION_OPTIONS } from '@/lib/labels';
import type { StudentProfile } from '@/types/api';

/** Only the fields the API accepts from a student on their own record. */
const EDITABLE = [
  'date_of_birth',
  'address_line1',
  'address_line2',
  'city',
  'state',
  'country',
  'postal_code',
  'qualification',
  'institution',
  'graduation_year',
  'emergency_contact_name',
  'emergency_contact_phone',
  'emergency_contact_relationship',
  'guardian_name',
  'guardian_phone',
] as const;

type Editable = (typeof EDITABLE)[number];

export function StudentProfileForm() {
  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getOwnStudentProfile()
      .then((loaded) => {
        if (cancelled) return;
        setProfile(loaded);
        setValues(
          Object.fromEntries(
            EDITABLE.map((field) => [field, String(loaded[field] ?? '')]),
          ),
        );
      })
      .catch((cause: unknown) => {
        if (!cancelled) setLoadError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function set(field: Editable, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    setSaved(false);
    try {
      // Empty strings are sent as-is for text fields, but nullable columns need
      // an explicit null rather than "".
      const payload: Record<string, unknown> = {};
      for (const field of EDITABLE) {
        const value = values[field] ?? '';
        payload[field] =
          value === '' && (field === 'date_of_birth' || field === 'graduation_year')
            ? null
            : value;
      }
      setProfile(await updateOwnStudentProfile(payload as Partial<StudentProfile>));
      setSaved(true);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading your student profile…" rows={5} />;
  if (loadError) {
    return (
      <ErrorState
        title="Could not load your profile"
        message={loadError.message}
        requestId={loadError.requestId || undefined}
      />
    );
  }
  if (!profile) return null;

  return (
    <Card className="animate-rise-in">
      <CardHeader>
        <CardTitle>Student profile</CardTitle>
        <CardDescription>
          <span className="font-mono">{profile.student_id}</span> · {profile.completion_percent}%
          complete
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Fee status:</span>
          <Badge variant={FEE_STATUS_VARIANT[profile.fee_status]}>
            {FEE_STATUS_LABEL[profile.fee_status]}
          </Badge>
          {/* Read-only by design: only an administrator may change it. */}
          <span className="text-xs text-muted-foreground">
            Maintained by the administration office.
          </span>
        </div>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          {saved ? <Alert variant="success">Your profile was saved.</Alert> : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Date of birth" htmlFor="dob" error={errors.date_of_birth}>
              <Input
                type="date"
                value={values.date_of_birth ?? ''}
                onChange={(event) => set('date_of_birth', event.target.value)}
              />
            </Field>
            <Field label="Highest qualification" htmlFor="qualification" error={errors.qualification}>
              <Select
                value={values.qualification ?? ''}
                onChange={(event) => set('qualification', event.target.value)}
              >
                <option value="">Not specified</option>
                {QUALIFICATION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="College or institution" htmlFor="institution" error={errors.institution}>
              <Input
                value={values.institution ?? ''}
                onChange={(event) => set('institution', event.target.value)}
              />
            </Field>
            <Field label="Graduation year" htmlFor="graduation-year" error={errors.graduation_year}>
              <Input
                type="number"
                min={1950}
                max={2100}
                value={values.graduation_year ?? ''}
                onChange={(event) => set('graduation_year', event.target.value)}
              />
            </Field>
          </div>

          <fieldset className="space-y-4">
            <legend className="text-sm font-medium">Address</legend>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Address line 1" htmlFor="address1" error={errors.address_line1}>
                <Input
                  value={values.address_line1 ?? ''}
                  onChange={(event) => set('address_line1', event.target.value)}
                />
              </Field>
              <Field label="Address line 2" htmlFor="address2" error={errors.address_line2}>
                <Input
                  value={values.address_line2 ?? ''}
                  onChange={(event) => set('address_line2', event.target.value)}
                />
              </Field>
              <Field label="City" htmlFor="city" error={errors.city}>
                <Input value={values.city ?? ''} onChange={(event) => set('city', event.target.value)} />
              </Field>
              <Field label="State" htmlFor="state" error={errors.state}>
                <Input value={values.state ?? ''} onChange={(event) => set('state', event.target.value)} />
              </Field>
              <Field label="Country" htmlFor="country" error={errors.country}>
                <Input
                  value={values.country ?? ''}
                  onChange={(event) => set('country', event.target.value)}
                />
              </Field>
              <Field label="Postal code" htmlFor="postal" error={errors.postal_code}>
                <Input
                  value={values.postal_code ?? ''}
                  onChange={(event) => set('postal_code', event.target.value)}
                />
              </Field>
            </div>
          </fieldset>

          <fieldset className="space-y-4">
            <legend className="text-sm font-medium">Emergency and guardian contact</legend>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Emergency contact name" htmlFor="ec-name" error={errors.emergency_contact_name}>
                <Input
                  value={values.emergency_contact_name ?? ''}
                  onChange={(event) => set('emergency_contact_name', event.target.value)}
                />
              </Field>
              <Field
                label="Emergency contact phone"
                htmlFor="ec-phone"
                error={errors.emergency_contact_phone}
                hint="International format, e.g. +919876543210"
              >
                <Input
                  value={values.emergency_contact_phone ?? ''}
                  onChange={(event) => set('emergency_contact_phone', event.target.value)}
                />
              </Field>
              <Field label="Relationship" htmlFor="ec-rel" error={errors.emergency_contact_relationship}>
                <Input
                  value={values.emergency_contact_relationship ?? ''}
                  onChange={(event) => set('emergency_contact_relationship', event.target.value)}
                />
              </Field>
              <Field label="Guardian name" htmlFor="guardian-name" error={errors.guardian_name}>
                <Input
                  value={values.guardian_name ?? ''}
                  onChange={(event) => set('guardian_name', event.target.value)}
                />
              </Field>
              <Field label="Guardian phone" htmlFor="guardian-phone" error={errors.guardian_phone}>
                <Input
                  value={values.guardian_phone ?? ''}
                  onChange={(event) => set('guardian_phone', event.target.value)}
                />
              </Field>
            </div>
          </fieldset>

          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Save profile'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
