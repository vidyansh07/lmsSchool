'use client';

import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import { getEffectivePolicy, getGlobalPolicy, updateGlobalPolicy } from '@/lib/academics';
import type { AcademicPolicy, EffectivePolicy } from '@/types/api';

/** The rules, and what they resolve to. Every field may be left to inherit. */
const PERCENT_FIELDS = [
  ['minimum_attendance_percent', 'Minimum attendance %'],
  ['passing_percent', 'Passing %'],
  ['minimum_assignment_completion_percent', 'Minimum assignments completed %'],
  ['minimum_test_average_percent', 'Minimum test average %'],
  ['minimum_lesson_completion_percent', 'Minimum lessons completed %'],
] as const;

const NUMBER_FIELDS = [
  ['assignment_default_max_marks', 'Default assignment marks'],
  ['test_default_max_marks', 'Default test marks'],
  ['assignment_default_max_attempts', 'Default assignment attempts'],
] as const;

const FLAG_FIELDS = [
  ['attendance_required_for_completion', 'Attendance required to complete'],
  ['assignment_required_for_completion', 'Assignments required to complete'],
  ['tests_required_for_completion', 'Tests required to complete'],
  ['assignment_allow_late', 'Allow late submission by default'],
] as const;

function AcademicRules() {
  const [policy, setPolicy] = useState<AcademicPolicy | null>(null);
  const [effective, setEffective] = useState<EffectivePolicy | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  function fill(row: AcademicPolicy) {
    setPolicy(row);
    const values: Record<string, string> = {};
    for (const [name] of [...PERCENT_FIELDS, ...NUMBER_FIELDS]) {
      const value = row[name];
      values[name] = value === null || value === undefined ? '' : String(value);
    }
    for (const [name] of FLAG_FIELDS) {
      const value = row[name];
      values[name] = value === null || value === undefined ? '' : String(value);
    }
    setForm(values);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([getGlobalPolicy(), getEffectivePolicy()])
      .then(([row, resolved]) => {
        if (cancelled) return;
        fill(row);
        setEffective(resolved);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    setNotice(null);
    const changes: Record<string, unknown> = {};
    for (const [name] of [...PERCENT_FIELDS, ...NUMBER_FIELDS]) {
      changes[name] = form[name] === '' ? null : form[name];
    }
    for (const [name] of FLAG_FIELDS) {
      changes[name] = form[name] === '' ? null : form[name] === 'true';
    }
    try {
      fill(await updateGlobalPolicy(changes));
      setEffective(await getEffectivePolicy());
      setNotice('Rules saved. They apply from the next request.');
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading the rules…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the academic rules"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!policy) return null;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Academic rules</h1>
        <p className="text-sm text-muted-foreground">
          Institution-wide settings. Leave a field empty to fall back to the built-in default. A
          course can override any of these.
        </p>
      </div>

      {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
          <CardDescription>
            These decide pass marks, attendance requirements and the defaults new work is created
            with. No deployment is needed to change them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={save}>
            {PERCENT_FIELDS.map(([name, label]) => (
              <Field key={name} label={label} htmlFor={name} error={errors[name]}>
                <Input
                  id={name}
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={form[name] ?? ''}
                  onChange={(event) => setForm({ ...form, [name]: event.target.value })}
                />
              </Field>
            ))}

            {NUMBER_FIELDS.map(([name, label]) => (
              <Field key={name} label={label} htmlFor={name} error={errors[name]}>
                <Input
                  id={name}
                  type="number"
                  min="1"
                  step={name === 'assignment_default_max_attempts' ? '1' : '0.01'}
                  value={form[name] ?? ''}
                  onChange={(event) => setForm({ ...form, [name]: event.target.value })}
                />
              </Field>
            ))}

            {FLAG_FIELDS.map(([name, label]) => (
              <Field key={name} label={label} htmlFor={name} error={errors[name]}>
                <Select
                  id={name}
                  value={form[name] ?? ''}
                  onChange={(event) => setForm({ ...form, [name]: event.target.value })}
                >
                  <option value="">Use the default</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </Select>
              </Field>
            ))}

            <div className="sm:col-span-2">
              <Button type="submit" disabled={isSaving}>
                {isSaving ? 'Saving…' : 'Save rules'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {effective ? (
        <Card>
          <CardHeader>
            <CardTitle>In force right now</CardTitle>
            <CardDescription>
              After course overrides, institution settings and built-in defaults.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              {Object.entries(effective).map(([name, value]) => (
                <div key={name}>
                  <dt className="text-muted-foreground">{name.replace(/_/g, ' ')}</dt>
                  <dd className="font-medium">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default function AcademicRulesPage() {
  return (
    <RequireAuth>
      <AcademicRules />
    </RequireAuth>
  );
}
