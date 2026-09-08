'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { ApiError, errorMessage } from '@/lib/api';
import { formatDateTime } from '@/lib/academic-labels';
import {
  getNotificationPreferences,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  updateNotificationPreferences,
} from '@/lib/communication';
import type { AppNotification, NotificationPreference } from '@/types/api';

const CATEGORY_LABEL: Record<string, string> = {
  academic: 'Coursework and results',
  schedule: 'Classes, tests and deadlines',
  announcements: 'Announcements',
  administrative: 'Completion and certificates',
};

const EMAIL_SWITCHES = [
  ['email_academic', 'Coursework and results'],
  ['email_schedule', 'Classes, tests and deadlines'],
  ['email_announcements', 'Announcements'],
  ['email_administrative', 'Completion and certificates'],
] as const;

/** Everything the product has told this person, and which of it reaches them by email. */
function Notifications() {
  const [rows, setRows] = useState<AppNotification[]>([]);
  const [preferences, setPreferences] = useState<NotificationPreference | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [page, prefs] = await Promise.all([
      listNotifications(),
      getNotificationPreferences(),
    ]);
    setRows(page.results);
    setPreferences(prefs);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listNotifications(), getNotificationPreferences()])
      .then(([page, prefs]) => {
        if (cancelled) return;
        setRows(page.results);
        setPreferences(prefs);
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

  async function run(key: string, action: () => Promise<unknown>) {
    setBusy(key);
    setFormError(null);
    try {
      await action();
      await load();
    } catch (cause) {
      setFormError(errorMessage(cause, 'That could not be done.'));
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading your notifications…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your notifications"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  const unread = rows.filter((row) => !row.is_read).length;

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Notifications</h1>
          <p className="text-sm text-muted-foreground">
            {unread === 0 ? 'Nothing unread.' : `${unread} unread.`}
          </p>
        </div>
        {unread > 0 ? (
          <Button
            type="button"
            variant="outline"
            disabled={busy === 'all'}
            onClick={() => run('all', markAllNotificationsRead)}
          >
            Mark everything read
          </Button>
        ) : null}
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing yet"
          description="Deadlines, results and announcements appear here."
        />
      ) : (
        <div className="stagger space-y-2">
          {rows.map((row) => (
            <div
              key={row.id}
              data-testid="notification-row"
              className={`animate-rise-in rounded-md border p-3 ${
                row.is_read ? 'border-border' : 'border-primary/40 bg-primary/5'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="neutral">{CATEGORY_LABEL[row.category] ?? row.category}</Badge>
                {row.is_read ? null : <Badge variant="warning">Unread</Badge>}
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(row.created_at)}
                </span>
              </div>
              <p className="mt-1 font-medium">{row.title}</p>
              {row.body ? (
                <p className="text-sm text-muted-foreground">{row.body}</p>
              ) : null}
              <div className="mt-2 flex flex-wrap gap-2">
                {row.link_path ? (
                  <Button asChild size="sm" variant="outline">
                    <Link href={row.link_path}>Open</Link>
                  </Button>
                ) : null}
                {row.is_read ? null : (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={busy === row.id}
                    onClick={() => run(row.id, () => markNotificationRead(row.id))}
                  >
                    Mark read
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {preferences ? (
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Email settings</CardTitle>
            <CardDescription>
              Turning a category off stops the emails. You still see everything here.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {EMAIL_SWITCHES.map(([name, label]) => (
              <Field key={name} label={label} htmlFor={name}>
                <label className="flex items-center gap-2 text-sm" htmlFor={name}>
                  <input
                    id={name}
                    data-testid={name}
                    type="checkbox"
                    checked={preferences[name]}
                    disabled={busy === name}
                    onChange={(event) =>
                      run(name, () =>
                        updateNotificationPreferences({ [name]: event.target.checked }),
                      )
                    }
                  />
                  Send me these by email
                </label>
              </Field>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default function NotificationsPage() {
  return (
    <RequireAuth>
      <Notifications />
    </RequireAuth>
  );
}
