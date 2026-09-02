'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import { changePassword, logoutEverywhere } from '@/lib/auth';

function SecuritySettings() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [revokeMessage, setRevokeMessage] = useState('');

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmation) {
      setErrors({ confirmation: 'The two passwords do not match.' });
      return;
    }
    setIsSaving(true);
    setErrors({});
    setMessage('');
    try {
      const response = await changePassword(currentPassword, newPassword);
      setMessage(response.detail);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmation('');
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  async function onRevoke() {
    try {
      const response = await logoutEverywhere();
      setRevokeMessage(response.detail);
      // Signing out everywhere includes this browser, so send the user to the
      // sign-in page rather than leaving a dead session on screen.
      router.replace('/login');
    } catch (cause) {
      setRevokeMessage(
        cause instanceof ApiError ? cause.message : 'Could not sign out of other sessions.',
      );
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Security</h1>
        <p className="text-sm text-muted-foreground">Manage your password and active sessions.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Change password</CardTitle>
          <CardDescription>
            Changing your password signs you out of every other device.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="max-w-md space-y-4" noValidate>
            {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
            {message ? <Alert variant="success">{message}</Alert> : null}

            <Field
              label="Current password"
              htmlFor="current-password"
              error={errors.current_password}
              required
            >
              <Input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </Field>
            <Field
              label="New password"
              htmlFor="new-password"
              error={errors.new_password}
              hint="At least 12 characters, and not a common password."
              required
            >
              <Input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </Field>
            <Field
              label="Confirm new password"
              htmlFor="confirm-password"
              error={errors.confirmation}
              required
            >
              <Input
                type="password"
                autoComplete="new-password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </Field>

            <Button type="submit" disabled={isSaving}>
              {isSaving ? 'Saving…' : 'Change password'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Active sessions</CardTitle>
          <CardDescription>
            Sign out of every device, including this one. Use this if you think someone else has
            access to your account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {revokeMessage ? (
            <Alert variant="info">
              <AlertTitle>{revokeMessage}</AlertTitle>
            </Alert>
          ) : null}
          <Button variant="destructive" onClick={() => void onRevoke()}>
            Sign out everywhere
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default function SecuritySettingsPage() {
  return (
    <RequireAuth>
      <SecuritySettings />
    </RequireAuth>
  );
}
