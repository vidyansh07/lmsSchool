'use client';

/**
 * A student's activities — the mock interviews, reviews, mentoring sessions
 * and feedback their trainers and counsellors chose to share with them
 * (docs/erp/USER_JOURNEYS.md §5.3).
 *
 * What "shared" means is the server's answer, not this page's:
 * `GET /students/<own id>/activities/` returns only
 * `student_visible_activities` for the student themself — never counselling
 * notes, follow-ups or placement calls — and `GET /activities/<id>/` reduces
 * the detail for a student caller (no reviewer note, no history actors, the
 * score only when the type shows it, and only the form answers marked
 * visible to students). Opening one is a read; there is nothing to write.
 *
 * `?activity=<id>` opens that one straight away — where a notification's
 * "Open" lands through `/activities/<id>`.
 */

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { FieldRenderer } from '@/components/forms/field-renderer';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select } from '@/components/ui/input';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { ACTIVITY_STATUS_LABEL, ACTIVITY_STATUS_VARIANT } from '@/lib/labels';
import { getActivity, listStudentActivities } from '@/lib/work';
import type { Activity, ActivityDetail, ActivityStatus, Paginated } from '@/types/api';

const RESULT_LABEL: Record<string, string> = {
  pass: 'Passed',
  fail: 'Not yet',
  mixed: 'Mixed',
};

type Show = 'all' | 'done';

function ActivityDetailSheet({
  activityId,
  onClose,
}: {
  activityId: string | null;
  onClose: () => void;
}) {
  const [state, setState] = useState<{
    id: string | null;
    detail: ActivityDetail | null;
    error: ApiError | null;
  }>({ id: activityId, detail: null, error: null });

  if (state.id !== activityId) setState({ id: activityId, detail: null, error: null });

  useEffect(() => {
    if (!activityId) return;
    let cancelled = false;
    getActivity(activityId)
      .then((detail) => {
        if (!cancelled) setState({ id: activityId, detail, error: null });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            id: activityId,
            detail: null,
            error:
              cause instanceof ApiError
                ? cause
                : new ApiError(0, 'error', 'Could not open this activity.', ''),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activityId]);

  const { detail, error } = state;
  // Only the answers the server shared: a field marked for staff stays out,
  // label and all, rather than appearing as an empty box.
  const sharedFields = detail?.form?.fields.filter((field) => field.visible_to_student) ?? [];

  return (
    <Sheet open={activityId !== null} onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent size="md">
        <SheetHeader>
          <SheetTitle>{detail?.title ?? 'Activity'}</SheetTitle>
        </SheetHeader>
        <div className="space-y-4 px-5 pb-6">
          {error ? (
            <ErrorState
              title={error.status === 404 ? 'This activity is not shared with you' : 'Could not open this activity'}
              message={
                error.status === 404
                  ? 'It may have been withdrawn, or it was never meant for students to see.'
                  : error.message
              }
              requestId={error.requestId || undefined}
            />
          ) : !detail ? (
            <LoadingState label="Opening the activity…" rows={3} />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{detail.type.name}</Badge>
                <Badge variant={ACTIVITY_STATUS_VARIANT[detail.status]}>
                  {ACTIVITY_STATUS_LABEL[detail.status]}
                </Badge>
                {detail.result !== 'n/a' && RESULT_LABEL[detail.result] ? (
                  <Badge variant={detail.result === 'pass' ? 'success' : 'warning'}>
                    {RESULT_LABEL[detail.result]}
                  </Badge>
                ) : null}
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-ink-muted">Due</dt>
                  <dd>{formatDateTime(detail.due_at)}</dd>
                </div>
                <div>
                  <dt className="text-ink-muted">Done</dt>
                  <dd>{formatDateTime(detail.completed_at)}</dd>
                </div>
                {detail.score !== null ? (
                  <div>
                    <dt className="text-ink-muted">Score</dt>
                    <dd className="tabular-nums">
                      {detail.score}
                      {detail.max_score ? ` / ${detail.max_score}` : ''}
                    </dd>
                  </div>
                ) : null}
                {detail.performed_by ? (
                  <div>
                    <dt className="text-ink-muted">With</dt>
                    <dd>{detail.performed_by.name}</dd>
                  </div>
                ) : null}
              </dl>
              {detail.summary ? (
                <div className="space-y-1">
                  <h3 className="text-sm font-medium">Summary</h3>
                  <p className="whitespace-pre-line text-sm">{detail.summary}</p>
                </div>
              ) : null}
              {sharedFields.length > 0 ? (
                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Feedback</h3>
                  <FieldRenderer fields={sharedFields} values={detail.form_values} readOnly />
                </div>
              ) : null}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function MyActivities() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const studentId = user?.role === 'student' ? user.profile_id : null;
  const [show, setShow] = useState<Show>('all');
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<string | null>(() => searchParams.get('activity'));
  const [attempt, setAttempt] = useState(0);
  const key = `${studentId}|${show}|${page}|${attempt}`;
  const [state, setState] = useState<{
    key: string;
    data: Paginated<Activity> | null;
    error: ApiError | null;
  }>({ key, data: null, error: null });

  if (state.key !== key) setState({ key, data: null, error: null });

  useEffect(() => {
    if (!studentId) return;
    let cancelled = false;
    listStudentActivities(studentId, {
      page,
      page_size: 20,
      ordering: '-created_at',
      ...(show === 'done' ? { status: 'completed' as ActivityStatus } : {}),
    })
      .then((data) => {
        if (!cancelled) setState({ key, data, error: null });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            key,
            data: null,
            error:
              cause instanceof ApiError
                ? cause
                : new ApiError(0, 'error', 'Could not load your activities.', ''),
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // `key` carries every input above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (user && user.role !== 'student') {
    return (
      <EmptyState
        title="This page is for students"
        description="Staff read activities on the Activities screen."
      />
    );
  }
  if (!studentId) {
    return (
      <EmptyState
        title="Your student record is not ready yet"
        description="Ask your counsellor to finish your registration."
      />
    );
  }

  const rows = state.data?.results ?? [];

  function openActivity(id: string | null) {
    setOpenId(id);
    // Keep the address in step so Back closes the sheet and the link can be shared.
    router.replace(id ? `/my-activities?activity=${encodeURIComponent(id)}` : '/my-activities');
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My activities</h1>
        <p className="text-sm text-ink-muted">
          Mock interviews, reviews, mentoring and feedback your trainers shared with you.
        </p>
      </div>

      <Card>
        <CardHeader className="flex-row flex-wrap items-end justify-between gap-3">
          <div className="space-y-1">
            <CardTitle as="h2">Shared with you</CardTitle>
            <CardDescription>Open one to read what was said and how it went.</CardDescription>
          </div>
          <div>
            <label htmlFor="my-activities-show" className="mb-1.5 block text-sm font-medium">
              Show
            </label>
            <Select
              id="my-activities-show"
              value={show}
              onChange={(event) => {
                setShow(event.target.value as Show);
                setPage(1);
              }}
            >
              <option value="all">Everything</option>
              <option value="done">Done</option>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {state.error ? (
            <ErrorState
              title="Could not load your activities"
              message={state.error.message}
              requestId={state.error.requestId || undefined}
              onRetry={() => setAttempt((value) => value + 1)}
            />
          ) : state.data === null ? (
            <LoadingState label="Loading your activities…" rows={4} />
          ) : rows.length === 0 ? (
            <EmptyState
              title={show === 'all' ? 'Nothing shared with you yet' : 'Nothing here'}
              description={
                show === 'all'
                  ? 'When a trainer shares a review or feedback with you, it appears here.'
                  : 'Try showing everything.'
              }
            />
          ) : (
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Activity</Th>
                    <Th>Type</Th>
                    <Th>Status</Th>
                    <Th>Due</Th>
                    <Th>Done</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="transition-colors hover:bg-sunken/40">
                      <Td>
                        <button
                          type="button"
                          className="text-left font-medium text-action hover:underline"
                          onClick={() => openActivity(row.id)}
                        >
                          {row.title}
                        </button>
                      </Td>
                      <Td>{row.type.name}</Td>
                      <Td>
                        <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]}>
                          {ACTIVITY_STATUS_LABEL[row.status]}
                        </Badge>
                      </Td>
                      <Td className="whitespace-nowrap text-ink-muted">{formatDateTime(row.due_at)}</Td>
                      <Td className="whitespace-nowrap text-ink-muted">
                        {formatDateTime(row.completed_at)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
          )}
          {state.data && state.data.total_pages > 1 ? (
            <Pagination
              page={state.data.page}
              totalPages={state.data.total_pages}
              count={state.data.count}
              pageSize={state.data.page_size}
              onPageChange={setPage}
            />
          ) : null}
        </CardContent>
      </Card>

      <ActivityDetailSheet activityId={openId} onClose={() => openActivity(null)} />
    </div>
  );
}

export default function MyActivitiesPage() {
  return (
    <RequireAuth>
      <Suspense fallback={<LoadingState label="Loading your activities…" rows={4} />}>
        <MyActivities />
      </Suspense>
    </RequireAuth>
  );
}

export { MyActivities };
