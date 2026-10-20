'use client';

/**
 * What can be done to many enrolments at once, from the admissions list:
 * export them, or move them to another batch.
 *
 * A transfer goes through `POST /enrollments/bulk-transfer/`, one student at a
 * time on the server, so a target that fills up partway leaves the rest where
 * they were and the result says who and why.
 */

import { useEffect, useState } from 'react';

import { SearchPicker, type PickerOption } from '@/components/admissions/search-picker';
import { TransferReasonFields } from '@/components/admissions/transfer-reason-fields';
import { useAuth } from '@/components/auth-provider';
import { BulkActionsBar, type BulkAction } from '@/components/bulk-actions';
import { BulkResultDialog } from '@/components/bulk-result-dialog';
import { ExportMenu } from '@/components/export-menu';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { UseBulkSelectionResult } from '@/hooks/use-bulk-selection';
import { fieldErrors } from '@/lib/api';
import { listEnrolmentDestinations } from '@/lib/batches';
import { formatDate } from '@/lib/batch-labels';
import { bulkTarget, bulkTransferEnrollments, type BulkResult } from '@/lib/bulk';
import { Capability } from '@/lib/capabilities';
import { formatCount } from '@/lib/format';
import type { ReportFilters } from '@/lib/reporting';
import type { BatchListRow } from '@/types/api';

export const ENROLLMENT_FILTER_KEYS = ['course', 'batch', 'status'] as const;

function TransferDialog({
  open,
  count,
  excludeBatchId,
  onClose,
  onTransfer,
}: {
  open: boolean;
  count: number;
  excludeBatchId?: string;
  onClose: () => void;
  onTransfer: (batchId: string, reason: string, isUpgrade: boolean) => Promise<Record<string, string> | null>;
}) {
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<BatchListRow[]>([]);
  const [target, setTarget] = useState<BatchListRow | null>(null);
  const [reason, setReason] = useState('');
  const [isUpgrade, setIsUpgrade] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      listEnrolmentDestinations({ search: query })
        .then(({ batches }) => setOptions(batches.filter((row) => row.id !== excludeBatchId)))
        .catch(() => setOptions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [open, query, excludeBatchId]);

  async function submit() {
    const missing: Record<string, string> = {};
    if (!target) missing.batch_id = 'Choose the batch they move to.';
    if (!reason.trim()) missing.reason = 'Say why these students are being moved.';
    if (Object.keys(missing).length > 0 || !target) {
      setErrors(missing);
      return;
    }
    setBusy(true);
    const refused = await onTransfer(target.id, reason.trim(), isUpgrade);
    setBusy(false);
    if (refused) {
      setErrors(refused);
      return;
    }
    setTarget(null);
    setReason('');
    setIsUpgrade(false);
    setErrors({});
  }

  const pickerOptions: PickerOption[] = options.map((row) => ({
    value: row.id,
    label: `${row.name} (${row.code})`,
    hint: `${row.course_title} · ${row.seats_available} left · starts ${formatDate(row.start_date)}`,
  }));
  const formError = errors.filters ?? errors.ids ?? errors.detail;
  const who = formatCount(count, 'student');

  return (
    <Dialog open={open} onOpenChange={(next) => (next || busy ? null : onClose())}>
      <DialogContent size="lg" className="max-h-[calc(100vh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Move {who} to another batch</DialogTitle>
          <DialogDescription>
            Each old enrolment is kept, marked Transferred, with its attendance. Anyone who cannot
            move — the batch fills up, or they are already finished — stays where they are and is
            listed.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {formError ? <Alert variant="error">{formError}</Alert> : null}
          <SearchPicker
            label="Move to batch"
            query={query}
            onQueryChange={setQuery}
            options={pickerOptions}
            selected={target?.id ?? ''}
            onSelect={(option) => setTarget(options.find((row) => row.id === option.value) ?? null)}
            placeholder="Batch name or code"
            emptyMessage="No batch open to enrolment matches that."
            error={errors.batch_id}
            required
          />
          {target && target.seats_available < count ? (
            <Alert variant="warning">
              Only {formatCount(target.seats_available, 'seat')} open on {target.name}; the rest will
              be skipped.
            </Alert>
          ) : null}
          <TransferReasonFields
            idPrefix="bulk-transfer"
            reason={reason}
            onReason={setReason}
            isUpgrade={isUpgrade}
            onUpgrade={setIsUpgrade}
            error={errors.reason}
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" disabled={busy} onClick={() => void submit()}>
            {busy ? 'Moving…' : `Move ${who}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EnrollmentBulkActions({
  selection,
  query,
  totalCount,
  exportFilters,
  allowSelectAllMatching,
  onChanged,
}: {
  selection: UseBulkSelectionResult<string>;
  query: Record<string, string | number | undefined>;
  totalCount: number | undefined;
  exportFilters: ReportFilters;
  /** False when a filter applies only to the page on screen (registration date). */
  allowSelectAllMatching: boolean;
  onChanged: () => void;
}) {
  const { can } = useAuth();
  const [transferring, setTransferring] = useState(false);
  const [result, setResult] = useState<BulkResult | null>(null);
  const mayTransfer = can(Capability.enrolmentCreate) && can(Capability.enrolmentUpdateAny);
  const count = selection.selectAllMatching ? (totalCount ?? 0) : selection.selectedCount;

  async function transfer(batchId: string, reason: string, isUpgrade: boolean) {
    try {
      const done = await bulkTransferEnrollments({
        ...bulkTarget(selection, query, ENROLLMENT_FILTER_KEYS),
        batch_id: batchId,
        reason,
        is_upgrade: isUpgrade,
      });
      setTransferring(false);
      setResult(done);
      selection.clear();
      onChanged();
      return null;
    } catch (cause) {
      return fieldErrors(cause);
    }
  }

  const actions: BulkAction[] = mayTransfer
    ? [{ id: 'transfer', label: 'Move to another batch', onClick: () => setTransferring(true) }]
    : [];

  return (
    <>
      <BulkActionsBar
        selectedCount={selection.selectedCount}
        totalMatchingCount={totalCount}
        selectAllMatching={selection.selectAllMatching}
        onSelectAllMatching={allowSelectAllMatching ? selection.selectAllMatchingFilter : undefined}
        onClear={selection.clear}
        actions={actions}
        itemNoun="enrolment"
      >
        <ExportMenu
          reportKey="enrollments"
          label={selection.selectAllMatching ? 'Export all matching' : 'Export'}
          filters={exportFilters}
          selectedIds={selection.selectAllMatching ? undefined : [...selection.selectedIds]}
        />
      </BulkActionsBar>
      <TransferDialog
        open={transferring}
        count={count}
        excludeBatchId={typeof query.batch === 'string' ? query.batch : undefined}
        onClose={() => setTransferring(false)}
        onTransfer={transfer}
      />
      <BulkResultDialog
        result={result}
        title="Moved to another batch"
        doneLabel="moved"
        itemNoun="enrolment"
        onClose={() => setResult(null)}
      />
    </>
  );
}
