'use client';

import Link from 'next/link';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { requestEmailVerification } from '@/lib/auth';
import { ROLE_LABEL } from '@/lib/labels';

function AccountSettings() {
  const { user } = useAuth();
  const [message, setMessage] = useState('');
  const [isSending, setIsSending] = useState(false);

  async function onVerify() {
    setIsSending(true);
    try {
      const response = await requestEmailVerification();
      setMessage(response.detail);
    } catch (cause) {
      setMessage(
        cause instanceof ApiError ? cause.message : 'Could not send the verification email.',
      );
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Account</h1>
        <p className="text-sm text-muted-foreground">Your sign-in details and account status.</p>
      </div>

      <Card className="animate-rise-in">
        <CardHeader>
          <CardTitle>Account details</CardTitle>
          <CardDescription>
            Your email address and role are managed by an administrator.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="divide-y divide-border text-sm">
            <div className="flex items-center justify-between gap-4 py-2">
              <dt className="text-muted-foreground">Email</dt>
              <dd className="font-medium">{user?.email}</dd>
            </div>
            <div className="flex items-center justify-between gap-4 py-2">
              <dt className="text-muted-foreground">Role</dt>
              <dd>
                <Badge>{user ? ROLE_LABEL[user.role] : ''}</Badge>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4 py-2">
              <dt className="text-muted-foreground">Account status</dt>
              <dd>
                <Badge variant={user?.is_active ? 'success' : 'error'}>
                  {user?.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4 py-2">
              <dt className="text-muted-foreground">Email verified</dt>
              <dd>
                <Badge variant={user?.is_email_verified ? 'success' : 'warning'}>
                  {user?.is_email_verified ? 'Verified' : 'Not verified'}
                </Badge>
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {!user?.is_email_verified ? (
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Verify your email address</CardTitle>
            <CardDescription>
              We will send a link to {user?.email}. It can be used once.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {message ? <Alert variant="info">{message}</Alert> : null}
            <Button onClick={() => void onVerify()} disabled={isSending}>
              {isSending ? 'Sending…' : 'Send verification email'}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Card className="animate-rise-in">
        <CardHeader>
          <CardTitle>Security</CardTitle>
          <CardDescription>Password and active sessions.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline">
            <Link href="/settings/security">Go to security settings</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default function AccountSettingsPage() {
  return (
    <RequireAuth>
      <AccountSettings />
    </RequireAuth>
  );
}
