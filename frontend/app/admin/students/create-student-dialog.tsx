'use client';

import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { INSTITUTION_KIND_OPTIONS, QUALIFICATION_OPTIONS } from '@/lib/labels';
import { createStudent } from '@/lib/people';
import type { InstitutionKind } from '@/types/api';

/**
 * Create a student account and profile in one step.
 *
 * No password field: the new student receives a single-use link and chooses
 * their own, so an administrator never handles someone else's credentials.
 */
export function CreateStudentDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [city, setCity] = useState('');
  const [qualification, setQualification] = useState('');
  const [institutionKind, setInstitutionKind] = useState<InstitutionKind | ''>('');
  const [institution, setInstitution] = useState('');
  const [feeAmount, setFeeAmount] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    try {
      await createStudent({
        email,
        first_name: firstName,
        last_name: lastName,
        phone,
        profile: { city, qualification, institution: institution.trim(), institution_kind: institutionKind },
        fee_amount: feeAmount.trim() === '' ? null : feeAmount.trim(),
      });
      onCreated();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card className="animate-rise-in">
      <CardHeader>
        <CardTitle>Add a student</CardTitle>
        <CardDescription>
          The student receives an email invitation and sets their own password.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Email" htmlFor="new-email" error={errors.email} required>
              <Input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>
            <Field label="Phone" htmlFor="new-phone" error={errors.phone}>
              <Input value={phone} onChange={(event) => setPhone(event.target.value)} />
            </Field>
            <Field label="First name" htmlFor="new-first" error={errors.first_name} required>
              <Input value={firstName} onChange={(event) => setFirstName(event.target.value)} />
            </Field>
            <Field label="Last name" htmlFor="new-last" error={errors.last_name}>
              <Input value={lastName} onChange={(event) => setLastName(event.target.value)} />
            </Field>
            <Field label="City" htmlFor="new-city" error={errors.city}>
              <Input value={city} onChange={(event) => setCity(event.target.value)} />
            </Field>
            <Field label="Qualification" htmlFor="new-qualification" error={errors.qualification}>
              <Select
                value={qualification}
                onChange={(event) => setQualification(event.target.value)}
              >
                <option value="">Not specified</option>
                {QUALIFICATION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Studying or working at" htmlFor="new-institution-kind" error={errors.institution_kind}>
              <Select
                value={institutionKind}
                onChange={(event) => setInstitutionKind(event.target.value as InstitutionKind | '')}
              >
                <option value="">Not specified</option>
                {INSTITUTION_KIND_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label={institutionKind === 'employer' ? 'Company name' : 'College name'}
              htmlFor="new-institution"
              error={errors.institution}
            >
              <Input value={institution} onChange={(event) => setInstitution(event.target.value)} />
            </Field>
            <Field
              label="Agreed fee (₹)"
              htmlFor="new-fee"
              error={errors.fee_amount}
              hint="Minimum ₹1,000. Leave blank if not decided yet."
            >
              <Input
                type="number"
                inputMode="decimal"
                min={1000}
                step="1"
                value={feeAmount}
                onChange={(event) => setFeeAmount(event.target.value)}
              />
            </Field>
          </div>

          <div className="flex gap-2">
            <Button type="submit" disabled={isSaving}>
              {isSaving ? 'Creating…' : 'Create student'}
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
