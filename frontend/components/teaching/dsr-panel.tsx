'use client';

/**
 * The daily status report: a form that arrives mostly filled in.
 *
 * `presentCount` / `absentCount` / `studentCount` are not read from the
 * fetched `DSR` — they are computed live from the register the trainer is
 * marking on the same screen, so they are always the count that will
 * actually be submitted, not a snapshot that can drift stale while the
 * trainer keeps correcting marks. Everything else here either mirrors what
 * the backend prefilled (`toWritePayload` in `lib/dsr.ts`) or starts blank
 * because there is nothing anywhere to prefill it from.
 *
 * Online/offline is the one pair of numbers this screen cannot compute (see
 * `register-editor.tsx`'s module docstring for why) but the backend still
 * requires *some* value for, defaulting to zero. Typing two digits is a
 * smaller ask than it sounds, but the two quick-fill buttons cover the
 * common case — a fully in-person or fully online class — in one press, so
 * typing is only needed for a genuinely mixed room.
 *
 * A report outside `EDITABLE_STATUSES` (submitted and beyond) renders as a
 * read summary, never a disabled form: a disabled input still looks like
 * something the trainer could fix if only they tried harder, where the truth
 * is that editing here is simply over.
 */
import { useId } from 'react';

import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import type { DSR, DSRStatus, DSRWritePayload } from '@/lib/dsr';
import { fallback, formatDateTime, formatNumber, NO_DATA } from '@/lib/format';

const DSR_STATUS_LABEL: Record<DSRStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  under_review: 'Under review',
  approved: 'Approved',
  rejected: 'Rejected',
  revision_required: 'Revision requested',
};

const DSR_STATUS_VARIANT: Record<DSRStatus, 'neutral' | 'success' | 'warning' | 'error'> = {
  draft: 'neutral',
  submitted: 'neutral',
  under_review: 'warning',
  approved: 'success',
  rejected: 'error',
  revision_required: 'warning',
};

function DraftStatus({
  isDirty,
  isSaving,
  lastSavedAt,
}: {
  isDirty: boolean;
  isSaving: boolean;
  lastSavedAt: string | null;
}) {
  if (isSaving) return <span className="text-xs text-muted-foreground">Saving draft…</span>;
  if (isDirty) return <span className="text-xs text-warning">Unsaved changes</span>;
  if (lastSavedAt) {
    return (
      <span className="text-xs text-muted-foreground">Draft saved {formatDateTime(lastSavedAt)}</span>
    );
  }
  return null;
}

export interface DsrPanelProps {
  dsr: DSR;
  draft: DSRWritePayload;
  onChange: (patch: DSRWritePayload) => void;
  presentCount: number;
  absentCount: number;
  studentCount: number;
  fieldErrors: Record<string, string>;
  isDirty: boolean;
  isSavingDraft: boolean;
  lastSavedAt: string | null;
}

export function DsrPanel({
  dsr,
  draft,
  onChange,
  presentCount,
  absentCount,
  studentCount,
  fieldErrors,
  isDirty,
  isSavingDraft,
  lastSavedAt,
}: DsrPanelProps) {
  const topicId = useId();
  const onlineId = useId();
  const offlineId = useId();
  const notesId = useId();
  const issuesId = useId();
  const concernsId = useId();

  if (!dsr.is_editable) {
    return (
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2">
          <CardTitle>Daily status report</CardTitle>
          <Badge variant={DSR_STATUS_VARIANT[dsr.status]}>{DSR_STATUS_LABEL[dsr.status]}</Badge>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            This report has moved on to review and can no longer be edited here.
          </p>
          {dsr.manager_comments ? (
            <Alert variant={dsr.status === 'rejected' ? 'error' : 'warning'}>
              {dsr.manager_comments}
            </Alert>
          ) : null}
          <p>{fallback(dsr.actual_topic, NO_DATA)}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>Daily status report</CardTitle>
        <DraftStatus isDirty={isDirty} isSaving={isSavingDraft} lastSavedAt={lastSavedAt} />
      </CardHeader>
      <CardContent className="space-y-4">
        {dsr.status === 'revision_required' && dsr.manager_comments ? (
          <Alert variant="warning" role="alert">
            <strong>Sent back for revision:</strong> {dsr.manager_comments}
          </Alert>
        ) : null}

        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span>
            <span className="text-muted-foreground">On roster: </span>
            <strong className="tabular-nums">{formatNumber(studentCount)}</strong>
          </span>
          <span>
            <span className="text-muted-foreground">Present: </span>
            <strong className="tabular-nums">{formatNumber(presentCount)}</strong>
          </span>
          <span>
            <span className="text-muted-foreground">Absent: </span>
            <strong className="tabular-nums">{formatNumber(absentCount)}</strong>
          </span>
        </div>

        <Field label="Topic for the report" htmlFor={topicId} error={fieldErrors.actual_topic}>
          <Input
            value={draft.actual_topic ?? ''}
            maxLength={250}
            onChange={(event) => onChange({ actual_topic: event.target.value })}
          />
        </Field>

        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium">How the room joined</span>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onChange({ offline_count: presentCount, online_count: 0 })}
              >
                All in person
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onChange({ online_count: presentCount, offline_count: 0 })}
              >
                All online
              </Button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Online" htmlFor={onlineId} error={fieldErrors.online_count}>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                value={draft.online_count ?? 0}
                onChange={(event) => onChange({ online_count: Number(event.target.value) || 0 })}
              />
            </Field>
            <Field label="Offline" htmlFor={offlineId} error={fieldErrors.offline_count}>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                value={draft.offline_count ?? 0}
                onChange={(event) => onChange({ offline_count: Number(event.target.value) || 0 })}
              />
            </Field>
          </div>
          <p className="text-xs text-muted-foreground">
            Not tracked automatically yet — confirm the split for this class.
          </p>
        </div>

        <Field label="Teaching notes" htmlFor={notesId} error={fieldErrors.teaching_notes} hint="Optional.">
          <Textarea
            rows={2}
            maxLength={2000}
            value={draft.teaching_notes ?? ''}
            onChange={(event) => onChange({ teaching_notes: event.target.value })}
          />
        </Field>

        <Field label="Issues" htmlFor={issuesId} error={fieldErrors.issues} hint="Optional.">
          <Textarea
            rows={2}
            maxLength={2000}
            value={draft.issues ?? ''}
            onChange={(event) => onChange({ issues: event.target.value })}
          />
        </Field>

        <Field
          label="Student concerns"
          htmlFor={concernsId}
          error={fieldErrors.student_concerns}
          hint="Optional."
        >
          <Textarea
            rows={2}
            maxLength={2000}
            value={draft.student_concerns ?? ''}
            onChange={(event) => onChange({ student_concerns: event.target.value })}
          />
        </Field>
      </CardContent>
    </Card>
  );
}
