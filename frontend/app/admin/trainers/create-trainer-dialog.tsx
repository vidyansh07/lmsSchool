'use client';

import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { createTrainer } from '@/lib/people';

export function CreateTrainerDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [title, setTitle] = useState('');
  const [skills, setSkills] = useState('');
  const [years, setYears] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    try {
      await createTrainer({
        email,
        first_name: firstName,
        last_name: lastName,
        profile: {
          professional_title: title,
          skills: skills
            .split(',')
            .map((entry) => entry.trim())
            .filter(Boolean),
          years_of_experience: years === '' ? null : Number(years),
        },
      });
      onCreated();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add a trainer</CardTitle>
        <CardDescription>
          The trainer receives an email invitation and sets their own password.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Email" htmlFor="t-email" error={errors.email} required>
              <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
            </Field>
            <Field label="Professional title" htmlFor="t-title" error={errors.professional_title}>
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label="First name" htmlFor="t-first" error={errors.first_name} required>
              <Input value={firstName} onChange={(event) => setFirstName(event.target.value)} />
            </Field>
            <Field label="Last name" htmlFor="t-last" error={errors.last_name}>
              <Input value={lastName} onChange={(event) => setLastName(event.target.value)} />
            </Field>
            <Field
              label="Skills"
              htmlFor="t-skills"
              error={errors.skills}
              hint="Comma separated, e.g. Linux, Python"
            >
              <Input value={skills} onChange={(event) => setSkills(event.target.value)} />
            </Field>
            <Field label="Years of experience" htmlFor="t-years" error={errors.years_of_experience}>
              <Input
                type="number"
                min={0}
                max={70}
                value={years}
                onChange={(event) => setYears(event.target.value)}
              />
            </Field>
          </div>

          <div className="flex gap-2">
            <Button type="submit" disabled={isSaving}>
              {isSaving ? 'Creating…' : 'Create trainer'}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
