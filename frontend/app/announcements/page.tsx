'use client';

import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { ApiError, errorMessage, fieldErrors } from '@/lib/api';
import { formatDateTime } from '@/lib/academic-labels';
import {
  archiveAnnouncement,
  createAnnouncement,
  listAnnouncements,
  publishAnnouncement,
} from '@/lib/communication';
import { listBatches } from '@/lib/batches';
import { Capability, can } from '@/lib/capabilities';
import type { Announcement, Audience, BatchListRow } from '@/types/api';

/** The noticeboard, and — for those who may write — the compose form. */
function Announcements() {
  const { user } = useAuth();
  const isStudent = user?.role === 'student';
  const mayAnnounceToAll = can(user?.capabilities, Capability.announcementManageAny);

  const [rows, setRows] = useState<Announcement[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [form, setForm] = useState({
    title: '',
    body: '',
    audience: 'batch' as Audience,
    batch: '',
    is_pinned: false,
  });

  const load = useCallback(async () => {
    setRows((await listAnnouncements()).results);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAnnouncements(), listBatches({ page_size: 100 }).catch(() => null)])
      .then(([page, batchPage]) => {
        if (cancelled) return;
        setRows(page.results);
        setBatches(batchPage?.results ?? []);
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

  async function run(key: string, action: () => Promise<unknown>, message: string) {
    setBusy(key);
    setFormError(null);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(message);
    } catch (cause) {
      setFormError(errorMessage(cause, 'That could not be done.'));
    } finally {
      setBusy(null);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy('create');
    setErrors({});
    try {
      await createAnnouncement({
        title: form.title,
        body: form.body,
        audience: form.audience,
        batch: form.audience === 'batch' ? form.batch : undefined,
        is_pinned: form.is_pinned,
      });
      setIsOpen(false);
      setForm({ ...form, title: '', body: '' });
      await load();
      setNotice('Saved as a draft. Publish it when you are ready.');
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading the noticeboard…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load announcements"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Announcements</h1>
          <p className="text-sm text-muted-foreground">
            {isStudent
              ? 'Notices for your courses and batches.'
              : 'What has been posted, and to whom.'}
          </p>
        </div>
        {isStudent ? null : (
          <Button type="button" onClick={() => setIsOpen((open) => !open)}>
            {isOpen ? 'Cancel' : 'New announcement'}
          </Button>
        )}
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}
      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      {isOpen ? (
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>New announcement</CardTitle>
            <CardDescription>
              It starts as a draft. Publishing puts it on the board and tells the people it is for.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

              <Field label="Title" htmlFor="title" error={errors.title}>
                <Input
                  id="title"
                  required
                  maxLength={200}
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                />
              </Field>

              <Field label="Message" htmlFor="body" error={errors.body}>
                <Textarea
                  id="body"
                  required
                  rows={4}
                  value={form.body}
                  onChange={(event) => setForm({ ...form, body: event.target.value })}
                />
              </Field>

              <Field label="Audience" htmlFor="audience" error={errors.audience}>
                <Select
                  id="audience"
                  value={form.audience}
                  onChange={(event) =>
                    setForm({ ...form, audience: event.target.value as Audience })
                  }
                >
                  <option value="batch">A batch</option>
                  {mayAnnounceToAll ? <option value="everyone">Everyone</option> : null}
                </Select>
              </Field>

              {form.audience === 'batch' ? (
                <Field label="Batch" htmlFor="batch" error={errors.batch}>
                  <Select
                    id="batch"
                    required
                    value={form.batch}
                    onChange={(event) => setForm({ ...form, batch: event.target.value })}
                  >
                    <option value="">Choose a batch…</option>
                    {batches.map((batch) => (
                      <option key={batch.id} value={batch.id}>
                        {batch.code} · {batch.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              ) : null}

              <Field label="Pin it" htmlFor="is_pinned">
                <label className="flex items-center gap-2 text-sm" htmlFor="is_pinned">
                  <input
                    id="is_pinned"
                    type="checkbox"
                    checked={form.is_pinned}
                    onChange={(event) => setForm({ ...form, is_pinned: event.target.checked })}
                  />
                  Keep it at the top of the board
                </label>
              </Field>

              <Button
                type="submit"
                disabled={busy === 'create' || (form.audience === 'batch' && !form.batch)}
              >
                {busy === 'create' ? 'Saving…' : 'Save as a draft'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState title="Nothing on the board" description="No announcements to show." />
      ) : (
        rows.map((row) => (
          <Card key={row.id} data-testid="announcement-card" className="animate-rise-in">
            <CardHeader className="gap-2">
              <div className="flex flex-wrap items-center gap-2">
                {row.is_pinned ? <Badge variant="warning">Pinned</Badge> : null}
                {row.status && row.status !== 'published' ? (
                  <Badge variant="neutral">{row.status}</Badge>
                ) : null}
                {row.batch_code ? (
                  <span className="font-mono text-xs text-muted-foreground">
                    {row.batch_code}
                  </span>
                ) : null}
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(row.published_at)}
                </span>
              </div>
              <CardTitle>{row.title}</CardTitle>
              <CardDescription>
                {row.created_by_name ? `Posted by ${row.created_by_name}` : ''}
                {row.course_title ? ` · ${row.course_title}` : ''}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="whitespace-pre-wrap text-sm">{row.body}</p>
              {!isStudent && row.status ? (
                <div className="flex flex-wrap gap-2">
                  {row.status === 'draft' ? (
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy === row.id}
                      onClick={() =>
                        run(
                          row.id,
                          () => publishAnnouncement(row.id),
                          'Published, and the audience has been told.',
                        )
                      }
                    >
                      Publish
                    </Button>
                  ) : null}
                  {row.status === 'published' ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy === row.id}
                      onClick={() =>
                        run(
                          row.id,
                          () => archiveAnnouncement(row.id),
                          'Taken off the board.',
                        )
                      }
                    >
                      Take it down
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

export default function AnnouncementsPage() {
  return (
    <RequireAuth>
      <Announcements />
    </RequireAuth>
  );
}
