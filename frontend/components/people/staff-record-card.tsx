'use client';

/**
 * What one staff member has been doing, between two dates.
 *
 * A counsellor's record is who they admitted and what they collected; a
 * trainer's is classes, reports and interviews; a placement officer's is the
 * candidates they moved. None of that is hard-coded per role — the card shows
 * the lines that counted something and drops the rest, so the shape of a
 * record says what the job was without anybody declaring it. A record listing
 * "0 class reports" beside "0 receipts" is a form, not a record.
 *
 * Who sees it: administrators for anybody, and each person for their own
 * (owner's decision, 26 October 2026). A manager does not, which is why this
 * card asks for `staff.view_record` *or* the viewer being the person — the
 * server enforces exactly the same pair, and the card going missing is a
 * courtesy rather than the control.
 *
 * The counters describe the whole span; the timeline is the most recent slice
 * of the detail behind them, and says so when it has been cut rather than
 * letting the length imply it.
 */

import { useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { errorMessage } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { formatDateTime, formatRupees, localIsoDate } from '@/lib/format';
import { getStaffRecord } from '@/lib/people';
import type { StaffRecord } from '@/types/api';

/** Turns `fee.payment.recorded` into "Fee payment recorded" — the audit
 *  action's own words, made readable, rather than a second vocabulary that
 *  has to be kept in step with the first. */
export function readableAction(action: string): string {
  const words = action.replace(/[._]/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function monthAgo(): string {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  return localIsoDate(date);
}

export function StaffRecordCard({
  userId,
  /** The person this record is about, so the card can tell "my own" from
   *  "somebody else's" without another request. */
  isSelf = false,
}: {
  userId: string;
  isSelf?: boolean;
}) {
  const { can } = useAuth();
  const mayRead = isSelf || can(Capability.staffViewRecord);

  const [start, setStart] = useState(monthAgo);
  const [end, setEnd] = useState(() => localIsoDate());
  const [record, setRecord] = useState<StaffRecord | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!mayRead) return undefined;
    let cancelled = false;
    getStaffRecord(userId, { start, end })
      .then((found) => {
        if (!cancelled) {
          setRecord(found);
          setFailure(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setFailure(errorMessage(cause, 'Could not read this record.'));
      });
    return () => {
      cancelled = true;
    };
  }, [userId, start, end, mayRead, attempt]);

  if (!mayRead) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle as="h2">{isSelf ? 'What you have done' : 'What they have done'}</CardTitle>
        <CardDescription>
          Counted from the record of who did the work, over the dates below.
          {isSelf ? null : ' Administrators and the person themselves can read this.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-3">
          <Field label="From" htmlFor="record-start">
            <Input
              id="record-start"
              type="date"
              value={start}
              max={end}
              onChange={(event) => setStart(event.target.value)}
            />
          </Field>
          <Field label="To" htmlFor="record-end">
            <Input
              id="record-end"
              type="date"
              value={end}
              min={start}
              onChange={(event) => setEnd(event.target.value)}
            />
          </Field>
        </div>

        {failure ? (
          <ErrorState message={failure} onRetry={() => setAttempt((value) => value + 1)} />
        ) : !record ? (
          <LoadingState label="Reading the record" rows={2} />
        ) : record.counters.length === 0 ? (
          <p className="text-sm text-ink-muted">
            Nothing recorded between these dates.
          </p>
        ) : (
          <>
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {record.counters.map((counter) => (
                <li key={counter.key} className="rounded-card border border-line px-3 py-2">
                  <p className="text-2xs uppercase tracking-wide text-ink-faint">
                    {counter.label}
                  </p>
                  <p className="text-lg font-semibold tabular-nums">
                    {counter.amount === null
                      ? counter.count
                      : formatRupees(Number(counter.amount))}
                  </p>
                  {counter.amount === null ? null : (
                    <p className="text-2xs text-ink-muted">
                      {counter.count} {counter.count === 1 ? 'receipt' : 'receipts'}
                    </p>
                  )}
                </li>
              ))}
            </ul>

            <div className="space-y-2">
              <h3 className="flex flex-wrap items-center gap-2 text-sm font-medium">
                Everything they did
                {record.timeline_truncated ? (
                  <Badge variant="neutral">the most recent {record.timeline.length}</Badge>
                ) : null}
              </h3>
              {record.timeline.length === 0 ? (
                <p className="text-sm text-ink-muted">Nothing between these dates.</p>
              ) : (
                <ol className="divide-y divide-line rounded-card border border-line">
                  {record.timeline.map((event) => (
                    <li
                      key={event.id}
                      className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-1.5 text-sm"
                    >
                      <span>
                        {readableAction(event.action)}
                        {event.resource_type ? (
                          <span className="text-ink-muted"> · {event.resource_type}</span>
                        ) : null}
                      </span>
                      <span className="text-2xs text-ink-faint">{formatDateTime(event.at)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
