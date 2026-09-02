'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import { formatDateTime } from '@/lib/academic-labels';
import { listThreads, startThread } from '@/lib/communication';
import { listMyEnrollments } from '@/lib/batches';
import type { DiscussionThread, Enrollment } from '@/types/api';

/** Questions on the batches the caller is part of. */
function Discussions() {
  const [rows, setRows] = useState<DiscussionThread[]>([]);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ batch: '', title: '', body: '' });

  useEffect(() => {
    let cancelled = false;
    Promise.all([listThreads(), listMyEnrollments().catch(() => [])])
      .then(([page, mine]) => {
        if (cancelled) return;
        setRows(page.results);
        setEnrollments(mine.filter((row) => row.grants_access));
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

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      await startThread(form.batch, { title: form.title, body: form.body });
      setIsOpen(false);
      setForm({ ...form, title: '', body: '' });
      setRows((await listThreads()).results);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading discussions…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load discussions"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Discussions</h1>
          <p className="text-sm text-muted-foreground">
            Questions on your batches, answered by your trainer and your classmates.
          </p>
        </div>
        {enrollments.length > 0 ? (
          <Button type="button" onClick={() => setIsOpen((open) => !open)}>
            {isOpen ? 'Cancel' : 'Ask a question'}
          </Button>
        ) : null}
      </div>

      {isOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>Ask a question</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

              <Field label="Batch" htmlFor="batch" error={errors.batch}>
                <Select
                  id="batch"
                  required
                  value={form.batch}
                  onChange={(event) => setForm({ ...form, batch: event.target.value })}
                >
                  <option value="">Choose a batch…</option>
                  {enrollments.map((row) => (
                    <option key={row.batch_id} value={row.batch_id}>
                      {row.batch_code} · {row.course_title}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Question" htmlFor="title" error={errors.title}>
                <Input
                  id="title"
                  required
                  maxLength={200}
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                />
              </Field>

              <Field label="Details" htmlFor="body" error={errors.body}>
                <Textarea
                  id="body"
                  required
                  rows={4}
                  value={form.body}
                  onChange={(event) => setForm({ ...form, body: event.target.value })}
                />
              </Field>

              <Button type="submit" disabled={busy || !form.batch}>
                {busy ? 'Posting…' : 'Post the question'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState
          title="No discussions yet"
          description="Ask the first question — your trainer is notified when you do."
        />
      ) : (
        <div className="space-y-2">
          {rows.map((row) => (
            <Card key={row.id} data-testid="thread-row">
              <CardContent className="space-y-1 pt-6">
                <div className="flex flex-wrap items-center gap-2">
                  {row.is_pinned ? <Badge variant="warning">Pinned</Badge> : null}
                  {row.is_closed ? <Badge variant="neutral">Closed</Badge> : null}
                  {row.has_trainer_reply ? (
                    <Badge variant="success">Answered</Badge>
                  ) : (
                    <Badge variant="neutral">Unanswered</Badge>
                  )}
                  <span className="font-mono text-xs text-muted-foreground">
                    {row.batch_code}
                  </span>
                </div>
                <Link
                  href={`/discussions/${row.id}`}
                  className="font-medium underline hover:text-foreground"
                >
                  {row.title}
                </Link>
                <p className="text-sm text-muted-foreground">
                  {row.author_name} · {row.reply_count} repl
                  {row.reply_count === 1 ? 'y' : 'ies'} ·{' '}
                  {formatDateTime(row.last_reply_at ?? row.created_at)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DiscussionsPage() {
  return (
    <RequireAuth>
      <Discussions />
    </RequireAuth>
  );
}
