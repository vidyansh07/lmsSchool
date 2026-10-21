'use client';

import { useEffect, useState } from 'react';

import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
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
  // What the student says about themselves. Everything above is a fact the
  // institute recorded; these are the questions only they can answer, and they
  // are asked because somebody uses the answers — a placement officer deciding
  // who to put in front of an employer, a planner deciding when a class runs.
  'about',
  'career_goal',
  'preferred_class_time',
  'linkedin_url',
  'github_url',
  'portfolio_url',
] as const;

/**
 * Lists, edited as one comma-separated line each.
 *
 * A tag widget would be nicer and is not what this needs: people type
 * "Linux, cloud, networking" without being taught to, it works on a phone
 * keyboard, and it survives a paste out of a CV. Split on save, joined on
 * load.
 */
const LIST_FIELDS = ['interests', 'skills', 'languages'] as const;

/** Yes/no answers, kept as strings so one state shape covers every field. */
const BOOLEAN_FIELDS = ['open_to_placement', 'willing_to_relocate'] as const;

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
        setValues({
          ...Object.fromEntries(
            EDITABLE.map((field) => [field, String(loaded[field] ?? '')]),
          ),
          ...Object.fromEntries(
            LIST_FIELDS.map((field) => [field, (loaded[field] ?? []).join(', ')]),
          ),
          ...Object.fromEntries(
            BOOLEAN_FIELDS.map((field) => [field, loaded[field] ? 'true' : 'false']),
          ),
        });
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

  function set(field: string, value: string) {
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
      for (const field of LIST_FIELDS) {
        // An empty line means an empty list, not a list holding "". Trimmed
        // because "Linux, cloud" is how people type it.
        payload[field] = (values[field] ?? '')
          .split(',')
          .map((entry) => entry.trim())
          .filter(Boolean);
      }
      for (const field of BOOLEAN_FIELDS) {
        payload[field] = values[field] === 'true';
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
    <Card className="">
      <CardHeader>
        <CardTitle>Student profile</CardTitle>
        <CardDescription>
          <span className="font-mono">{profile.student_id}</span> · {profile.completion_percent}%
          complete
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-ink-muted">Fee status:</span>
          <Badge variant={FEE_STATUS_VARIANT[profile.fee_status]}>
            {FEE_STATUS_LABEL[profile.fee_status]}
          </Badge>
          {/* Read-only by design: only an administrator may change it. */}
          <span className="text-xs text-ink-muted">
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

          {/* The part only the student can answer. Kept last because the
              fields above are the ones the office chases them for, and kept
              on the same form because a second page is a second thing to
              remember to save. */}
          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold text-ink">About you</legend>
            <p className="text-sm text-ink-muted">
              None of this is required. It is what we use to suggest the right
              course, to schedule classes at a time you can make, and — if you
              want it — to put you in front of employers.
            </p>
            <Field label="About you" htmlFor="about" error={errors.about}>
              <Textarea
                id="about"
                rows={3}
                value={values.about ?? ''}
                onChange={(event) => set('about', event.target.value)}
                placeholder="A few lines in your own words."
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="What do you want to do?"
                htmlFor="career-goal"
                error={errors.career_goal}
                hint="The job or field you are aiming for."
              >
                <Input
                  id="career-goal"
                  value={values.career_goal ?? ''}
                  onChange={(event) => set('career_goal', event.target.value)}
                  placeholder="e.g. Linux system administrator"
                />
              </Field>
              <Field
                label="When can you attend?"
                htmlFor="class-time"
                error={errors.preferred_class_time}
                hint="So we do not put you in a batch you cannot make."
              >
                <Select
                  id="class-time"
                  value={values.preferred_class_time ?? ''}
                  onChange={(event) => set('preferred_class_time', event.target.value)}
                >
                  <option value="">No preference</option>
                  <option value="morning">Morning</option>
                  <option value="afternoon">Afternoon</option>
                  <option value="evening">Evening</option>
                  <option value="weekend">Weekend</option>
                </Select>
              </Field>
              <Field
                label="Subjects you enjoy"
                htmlFor="interests"
                error={errors.interests}
                hint="Separate with commas."
              >
                <Input
                  id="interests"
                  value={values.interests ?? ''}
                  onChange={(event) => set('interests', event.target.value)}
                  placeholder="Linux, cloud, networking"
                />
              </Field>
              <Field
                label="What can you already do?"
                htmlFor="skills"
                error={errors.skills}
                hint="Separate with commas."
              >
                <Input
                  id="skills"
                  value={values.skills ?? ''}
                  onChange={(event) => set('skills', event.target.value)}
                  placeholder="Bash, Python, Git"
                />
              </Field>
              <Field
                label="Languages you speak"
                htmlFor="languages"
                error={errors.languages}
                hint="Separate with commas."
              >
                <Input
                  id="languages"
                  value={values.languages ?? ''}
                  onChange={(event) => set('languages', event.target.value)}
                  placeholder="Hindi, English"
                />
              </Field>
              <Field label="LinkedIn" htmlFor="linkedin" error={errors.linkedin_url}>
                <Input
                  id="linkedin"
                  type="url"
                  value={values.linkedin_url ?? ''}
                  onChange={(event) => set('linkedin_url', event.target.value)}
                  placeholder="https://…"
                />
              </Field>
              <Field label="GitHub" htmlFor="github" error={errors.github_url}>
                <Input
                  id="github"
                  type="url"
                  value={values.github_url ?? ''}
                  onChange={(event) => set('github_url', event.target.value)}
                  placeholder="https://…"
                />
              </Field>
              <Field label="Portfolio or website" htmlFor="portfolio" error={errors.portfolio_url}>
                <Input
                  id="portfolio"
                  type="url"
                  value={values.portfolio_url ?? ''}
                  onChange={(event) => set('portfolio_url', event.target.value)}
                  placeholder="https://…"
                />
              </Field>
            </div>
            <div className="space-y-2">
              {/* Opt-in, not opt-out: nobody should be put in front of an
                  employer because they forgot to untick something. */}
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[var(--color-action)]"
                  checked={values.open_to_placement === 'true'}
                  onChange={(event) =>
                    set('open_to_placement', event.target.checked ? 'true' : 'false')
                  }
                />
                <span>
                  I am looking for a job
                  <span className="block text-ink-muted">
                    Our placement team will see this and may put you forward.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[var(--color-action)]"
                  checked={values.willing_to_relocate === 'true'}
                  onChange={(event) =>
                    set('willing_to_relocate', event.target.checked ? 'true' : 'false')
                  }
                />
                <span>I would move city for the right job</span>
              </label>
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
