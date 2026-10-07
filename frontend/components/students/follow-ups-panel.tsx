'use client';

/**
 * The follow-ups on a student's record, told apart by what still needs doing.
 *
 * A follow-up is an activity of category `follow_up` (the seeded `follow-up`
 * type). "Pending" is every open status — assigned, in progress, overdue,
 * or an older draft — and "Completed" is done or approved. Marking one done
 * goes through the same `POST /activities/{id}/complete/` the activity
 * drawer uses, answering the seeded `follow-up-note` form (channel, outcome,
 * summary) in a dialog small enough for a counsellor between two calls.
 */
import { useEffect, useState } from 'react';
import { CheckCircle2, Phone } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Select, Textarea } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th, Tr } from '@/components/ui/table';
import { errorMessage, fieldErrors } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { ACTIVITY_STATUS_LABEL, ACTIVITY_STATUS_VARIANT } from '@/lib/labels';
import { completeActivity, listStudentActivities } from '@/lib/work';
import type { Activity, ActivityStatus } from '@/types/api';

const DONE: ReadonlySet<ActivityStatus> = new Set(['completed', 'approved', 'under_review']);
const CLOSED: ReadonlySet<ActivityStatus> = new Set(['cancelled', 'missed']);
/** The statuses the server lets a follow-up be completed from. */
const COMPLETABLE: ReadonlySet<ActivityStatus> = new Set(['assigned', 'in_progress', 'overdue']);

const CHANNELS = [
  ['phone', 'Phone'],
  ['whatsapp', 'WhatsApp'],
  ['email', 'Email'],
  ['in_person', 'In person'],
] as const;
const OUTCOMES = [
  ['reached', 'Reached'],
  ['no_answer', 'No answer'],
  ['callback', 'Call back later'],
  ['closed', 'Closed'],
] as const;

function MarkDoneForm({
  activity,
  onOpenChange,
  onDone,
}: {
  activity: Activity;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}) {
  const [channel, setChannel] = useState<string>('phone');
  const [outcome, setOutcome] = useState<string>('reached');
  const [summary, setSummary] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    setMessage('');
    try {
      await completeActivity(activity.id, {
        form_values: { channel, outcome, summary: summary.trim() },
        summary: summary.trim(),
      });
      onOpenChange(false);
      onDone();
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (Object.keys(fields).length === 0)
        setMessage(errorMessage(cause, 'Could not mark this follow-up done.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void save(event)} noValidate>
      <DialogHeader>
        <DialogTitle>Mark follow-up done</DialogTitle>
        <DialogDescription>
          {activity.title}
          {activity.due_at ? ` · was due ${formatDateTime(activity.due_at)}` : ''}
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-3">
        {message ? (
          <p className="text-sm text-danger" role="alert">
            {message}
          </p>
        ) : null}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="How" htmlFor="done-channel" error={errors.channel} required>
            <Select id="done-channel" value={channel} onChange={(event) => setChannel(event.target.value)}>
              {CHANNELS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Outcome" htmlFor="done-outcome" error={errors.outcome} required>
            <Select id="done-outcome" value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              {OUTCOMES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="What was said" htmlFor="done-summary" error={errors.summary}>
          <Textarea
            id="done-summary"
            rows={3}
            maxLength={1000}
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
          />
        </Field>
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" disabled={saving} onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Mark done'}
        </Button>
      </DialogFooter>
    </form>
  );
}

function FollowUpRows({
  rows,
  mayComplete,
  onMarkDone,
  emptyText,
}: {
  rows: Activity[];
  mayComplete: boolean;
  onMarkDone?: (activity: Activity) => void;
  emptyText: string;
}) {
  if (rows.length === 0) return <p className="text-sm text-ink-muted">{emptyText}</p>;
  return (
    <TableWrapper>
      <Table>
        <thead>
          <tr>
            <Th>Follow-up</Th>
            <Th>Due</Th>
            <Th>Status</Th>
            <Th>With</Th>
            {onMarkDone ? (
              <Th className="text-right">
                <span className="sr-only">Actions</span>
              </Th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <Tr key={row.id} data-testid={`follow-up-${row.id}`}>
              <Td>
                <a href={`/activities?id=${row.id}`} className="font-medium hover:underline">
                  {row.title}
                </a>
              </Td>
              <Td className="whitespace-nowrap">
                {row.completed_at
                  ? `Done ${formatDateTime(row.completed_at)}`
                  : row.due_at
                    ? formatDateTime(row.due_at)
                    : '—'}
              </Td>
              <Td>
                <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]} dot>
                  {ACTIVITY_STATUS_LABEL[row.status]}
                </Badge>
              </Td>
              <Td>{row.assigned_to?.name ?? '—'}</Td>
              {onMarkDone ? (
                <Td className="text-right">
                  {mayComplete && COMPLETABLE.has(row.status) ? (
                    <Button size="sm" variant="outline" onClick={() => onMarkDone(row)}>
                      <CheckCircle2 className="size-4" aria-hidden="true" />
                      Mark done
                    </Button>
                  ) : null}
                </Td>
              ) : null}
            </Tr>
          ))}
        </tbody>
      </Table>
    </TableWrapper>
  );
}

export function FollowUpsPanel({
  studentId,
  mayComplete,
  refreshKey = 0,
  action,
}: {
  studentId: string;
  mayComplete: boolean;
  /** Bump to reload — after "Plan a follow-up" created one, for instance. */
  refreshKey?: number;
  /** Rendered in the header: the "Plan a follow-up" button. */
  action?: React.ReactNode;
}) {
  const [state, setState] = useState<{ rows: Activity[]; loaded: boolean; error: string }>({
    rows: [],
    loaded: false,
    error: '',
  });
  const [marking, setMarking] = useState<Activity | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listStudentActivities(studentId, { category: 'follow_up', ordering: 'due_at', page_size: 50 })
      .then((page) => {
        if (!cancelled) setState({ rows: page.results, loaded: true, error: '' });
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setState((previous) => ({
            ...previous,
            loaded: true,
            error: errorMessage(cause, 'Could not load the follow-ups.'),
          }));
      });
    return () => {
      cancelled = true;
    };
  }, [studentId, refreshKey, reloads]);

  const { rows, loaded, error } = state;
  const loading = !loaded;

  const pending = rows.filter((row) => !DONE.has(row.status) && !CLOSED.has(row.status));
  const completed = rows.filter((row) => DONE.has(row.status));

  return (
    <Card data-testid="follow-ups-panel">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Phone className="size-4 text-ink-muted" aria-hidden="true" />
            Follow-ups
          </CardTitle>
          <CardDescription>
            {pending.length} pending · {completed.length} completed
          </CardDescription>
        </div>
        {action}
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        ) : null}
        {loading && rows.length === 0 ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : (
          <>
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">Pending</p>
              <FollowUpRows
                rows={pending}
                mayComplete={mayComplete}
                onMarkDone={setMarking}
                emptyText="Nothing pending."
              />
            </div>
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">
                Completed
              </p>
              <FollowUpRows rows={completed} mayComplete={false} emptyText="None completed yet." />
            </div>
          </>
        )}
      </CardContent>
      <Dialog open={marking !== null} onOpenChange={(open) => (open ? null : setMarking(null))}>
        <DialogContent>
          {marking ? (
            <MarkDoneForm
              activity={marking}
              onOpenChange={(open) => (open ? null : setMarking(null))}
              onDone={() => setReloads((value) => value + 1)}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
