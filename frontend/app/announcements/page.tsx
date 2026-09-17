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
  cancelAnnouncement,
  createAnnouncement,
  listAnnouncements,
  publishAnnouncement,
  scheduleAnnouncement,
} from '@/lib/communication';
import { listBatches } from '@/lib/batches';
import { listBranches } from '@/lib/organisation';
import { Capability, can } from '@/lib/capabilities';
import { ANNOUNCEMENT_STATUS_LABEL, ANNOUNCEMENT_STATUS_VARIANT, ROLE_OPTIONS } from '@/lib/labels';
import type { Announcement, Audience, BatchListRow, Branch, UserRole } from '@/types/api';

/** The noticeboard, and — for those who may write — the compose form. */
function Announcements() {
  const { user } = useAuth();
  const isStudent = user?.role === 'student';
  const mayAnnounceToAll = can(user?.capabilities, Capability.announcementManageAny);

  const [rows, setRows] = useState<Announcement[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
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
    role: (ROLE_OPTIONS[0]?.value ?? 'trainer') as UserRole,
    branch: '',
    is_pinned: false,
    // "Schedule for later" (ERP Phase 19): unset publishes immediately (the
    // existing "Save as a draft" → explicit "Publish" path is unchanged), set
    // moves the new draft straight to `scheduled` for that moment instead.
    publish_at: '',
  });

  const load = useCallback(async () => {
    setRows((await listAnnouncements()).results);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listAnnouncements(),
      listBatches({ page_size: 100 }).catch(() => null),
      listBranches({ page_size: 100 }).catch(() => null),
    ])
      .then(([page, batchPage, branchPage]) => {
        if (cancelled) return;
        setRows(page.results);
        setBatches(batchPage?.results ?? []);
        setBranches(branchPage?.results ?? []);
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
      const publishAt = form.publish_at ? new Date(form.publish_at).toISOString() : undefined;
      const created = await createAnnouncement({
        title: form.title,
        body: form.body,
        audience: form.audience,
        batch: form.audience === 'batch' ? form.batch : undefined,
        role: form.audience === 'role' ? form.role : undefined,
        branch: form.audience === 'branch' ? form.branch : undefined,
        is_pinned: form.is_pinned,
        publish_at: publishAt,
      });
      // A chosen date means "schedule it", not just "remember a date on the
      // draft" — the explicit `.../schedule/` call is what actually moves it
      // out of `draft` (`API_CONTRACTS.md`: "moves draft → scheduled").
      if (publishAt) await scheduleAnnouncement(created.id, publishAt);
      setIsOpen(false);
      setForm({ ...form, title: '', body: '', publish_at: '' });
      await load();
      setNotice(
        publishAt
          ? `Scheduled for ${formatDateTime(publishAt)}.`
          : 'Saved as a draft. Publish it when you are ready.',
      );
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
                  {mayAnnounceToAll ? <option value="trainers">Trainers at my centre</option> : null}
                  {mayAnnounceToAll ? <option value="role">Everyone in a role</option> : null}
                  {mayAnnounceToAll ? <option value="branch">A centre</option> : null}
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

              {form.audience === 'role' ? (
                <Field label="Role" htmlFor="announcement-role" error={errors.role}>
                  <Select
                    id="announcement-role"
                    required
                    value={form.role}
                    onChange={(event) => setForm({ ...form, role: event.target.value as UserRole })}
                  >
                    {ROLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              ) : null}

              {form.audience === 'branch' ? (
                <Field label="Centre" htmlFor="announcement-branch" error={errors.branch}>
                  <Select
                    id="announcement-branch"
                    required
                    value={form.branch}
                    onChange={(event) => setForm({ ...form, branch: event.target.value })}
                  >
                    <option value="">Choose a centre…</option>
                    {branches.map((branch) => (
                      <option key={branch.id} value={branch.id}>
                        {branch.code} · {branch.name}
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

              <Field
                label="Schedule for later"
                htmlFor="announcement-publish-at"
                hint="Leave blank to save as a draft and publish it yourself when ready."
                error={errors.publish_at}
              >
                <Input
                  id="announcement-publish-at"
                  type="datetime-local"
                  value={form.publish_at}
                  onChange={(event) => setForm({ ...form, publish_at: event.target.value })}
                />
              </Field>

              <Button
                type="submit"
                disabled={
                  busy === 'create' ||
                  (form.audience === 'batch' && !form.batch) ||
                  (form.audience === 'role' && !form.role) ||
                  (form.audience === 'branch' && !form.branch)
                }
              >
                {busy === 'create'
                  ? 'Saving…'
                  : form.publish_at
                    ? 'Schedule'
                    : 'Save as a draft'}
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
                  <Badge variant={ANNOUNCEMENT_STATUS_VARIANT[row.status]}>
                    {ANNOUNCEMENT_STATUS_LABEL[row.status]}
                  </Badge>
                ) : null}
                {row.batch_code ? (
                  <span className="font-mono text-xs text-muted-foreground">
                    {row.batch_code}
                  </span>
                ) : null}
                {row.role_name ? (
                  <span className="text-xs text-muted-foreground">{row.role_name}</span>
                ) : null}
                {row.branch_name ? (
                  <span className="text-xs text-muted-foreground">{row.branch_name}</span>
                ) : null}
                <span className="text-xs text-muted-foreground">
                  {row.status === 'scheduled'
                    ? `Scheduled for ${formatDateTime(row.publish_at)}`
                    : formatDateTime(row.published_at)}
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
                  {row.status === 'scheduled' ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busy === row.id}
                      onClick={() =>
                        run(row.id, () => cancelAnnouncement(row.id), 'Schedule cancelled.')
                      }
                    >
                      Cancel schedule
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
