'use client';

import { Checkbox } from '@/components/ui/checkbox';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';

/**
 * Why a student is being moved, and whether it is an upgrade — asked by every
 * transfer (one student, a batch, a selection on the admissions list) and kept
 * on the old enrolment, so the move never reads as a drop-out.
 */
export function TransferReasonFields({
  idPrefix,
  reason,
  onReason,
  isUpgrade,
  onUpgrade,
  error,
}: {
  idPrefix: string;
  reason: string;
  onReason: (value: string) => void;
  isUpgrade: boolean;
  onUpgrade: (value: boolean) => void;
  error?: string;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
      <Field
        label="Reason"
        htmlFor={`${idPrefix}-reason`}
        error={error}
        hint="Kept on the old enrolment, so the move never reads as a drop-out."
        required
      >
        <Input
          id={`${idPrefix}-reason`}
          value={reason}
          maxLength={255}
          placeholder="e.g. Evening batch suits their job"
          onChange={(event) => onReason(event.target.value)}
        />
      </Field>
      <label className="flex items-center gap-2 pb-2 text-sm">
        <Checkbox checked={isUpgrade} onCheckedChange={(value) => onUpgrade(Boolean(value))} />
        An upgrade to a longer or different programme
      </label>
    </div>
  );
}
