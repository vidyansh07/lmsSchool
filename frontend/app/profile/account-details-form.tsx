'use client';

import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { updateCurrentUser } from '@/lib/auth';

/**
 * Name and phone only.
 *
 * Email, role and account status are absent because a user may not change them
 * — and the API would reject them anyway, naming the offending field.
 */
export function AccountDetailsForm() {
  const { user, setUser } = useAuth();
  const [firstName, setFirstName] = useState(user?.first_name ?? '');
  const [lastName, setLastName] = useState(user?.last_name ?? '');
  const [phone, setPhone] = useState(user?.phone ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    setSaved(false);
    try {
      setUser(
        await updateCurrentUser({ first_name: firstName, last_name: lastName, phone }),
      );
      setSaved(true);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card className="animate-rise-in">
      <CardHeader>
        <CardTitle>Account details</CardTitle>
        <CardDescription>
          Your email address and role are managed by an administrator.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          {saved ? <Alert variant="success">Your details were saved.</Alert> : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="First name" htmlFor="first-name" error={errors.first_name} required>
              <Input value={firstName} onChange={(event) => setFirstName(event.target.value)} />
            </Field>
            <Field label="Last name" htmlFor="last-name" error={errors.last_name}>
              <Input value={lastName} onChange={(event) => setLastName(event.target.value)} />
            </Field>
            <Field
              label="Phone"
              htmlFor="phone"
              error={errors.phone}
              hint="International format, e.g. +919876543210"
            >
              <Input value={phone} onChange={(event) => setPhone(event.target.value)} />
            </Field>
            <Field label="Email" htmlFor="email-readonly">
              <Input value={user?.email ?? ''} readOnly disabled />
            </Field>
          </div>

          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Save changes'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
