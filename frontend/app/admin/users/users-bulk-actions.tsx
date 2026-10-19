'use client';

/**
 * What can be done to many accounts at once, from the accounts list: export
 * them, resend their invitations, move them to a centre.
 *
 * Each action works on the ticked rows, or on every account the filters match
 * once "select all matching" is chosen — the server resolves that from the
 * same filters (`POST /users/bulk/`), it is never a page of ids pretending to
 * be everything. Each account still goes through the single-account rules,
 * and the result dialog says which were skipped and why.
 */

import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { BulkActionsBar, type BulkAction } from '@/components/bulk-actions';
import { BulkResultDialog } from '@/components/bulk-result-dialog';
import { ExportMenu } from '@/components/export-menu';
import { useResendInvitations } from '@/components/resend-invitations-action';
import { useBranches } from '@/components/organisation/branch-field';
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
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import type { UseBulkSelectionResult } from '@/hooks/use-bulk-selection';
import { fieldErrors } from '@/lib/api';
import { bulkTarget, bulkUsers, type BulkResult } from '@/lib/bulk';
import { Capability } from '@/lib/capabilities';
import { formatCount } from '@/lib/format';
import { exportFiltersFrom } from '@/lib/reporting';

export const USER_FILTER_KEYS = [
  'role',
  'is_active',
  'is_email_verified',
  'invitation_accepted',
  'branch',
] as const;

type Pending = 'move' | null;

export function UsersBulkActions({
  selection,
  query,
  totalCount,
  onChanged,
}: {
  selection: UseBulkSelectionResult<string>;
  query: Record<string, string | number | undefined>;
  totalCount: number | undefined;
  onChanged: () => void;
}) {
  const { can } = useAuth();
  const mayMove = can(Capability.organisationAssignUsers);
  const { branches } = useBranches(mayMove);
  const [pending, setPending] = useState<Pending>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ title: string; done: string; value: BulkResult } | null>(
    null,
  );
  const [branchId, setBranchId] = useState('');
  const [reason, setReason] = useState('');
  const [moveErrors, setMoveErrors] = useState<Record<string, string>>({});

  const count = selection.selectAllMatching ? (totalCount ?? 0) : selection.selectedCount;
  const who = formatCount(count, 'account');
  const target = bulkTarget(selection, query, USER_FILTER_KEYS);
  const resend = useResendInvitations({
    count,
    itemNoun: 'account',
    send: () => bulkUsers({ ...target, action: 'resend_invitation' }),
    onDone: () => {
      selection.clear();
      onChanged();
    },
  });

  function finished(title: string, done: string, value: BulkResult) {
    setResult({ title, done, value });
    selection.clear();
    onChanged();
  }

  async function move(event: React.FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!branchId) missing.branch_id = 'Choose the centre.';
    if (!reason.trim()) missing.reason = 'Say why; it goes in the audit trail.';
    if (Object.keys(missing).length > 0) {
      setMoveErrors(missing);
      return;
    }
    setBusy(true);
    setMoveErrors({});
    try {
      const value = await bulkUsers({
        ...target,
        action: 'move_centre',
        branch_id: branchId,
        reason: reason.trim(),
      });
      setPending(null);
      setBranchId('');
      setReason('');
      finished('Centre move', 'moved', value);
    } catch (cause) {
      setMoveErrors(fieldErrors(cause));
    } finally {
      setBusy(false);
    }
  }

  const actions: BulkAction[] = [];
  if (can(Capability.userUpdateAny)) {
    actions.push({ id: 'resend', label: 'Resend invitations', onClick: resend.open });
  }
  if (mayMove && branches.length > 1) {
    actions.push({ id: 'move', label: 'Move to a centre', onClick: () => setPending('move') });
  }

  const formError = moveErrors.filters ?? moveErrors.ids ?? moveErrors.detail ?? moveErrors.non_field_errors;

  return (
    <>
      <BulkActionsBar
        selectedCount={selection.selectedCount}
        totalMatchingCount={totalCount}
        selectAllMatching={selection.selectAllMatching}
        onSelectAllMatching={selection.selectAllMatchingFilter}
        onClear={selection.clear}
        actions={actions}
        itemNoun="account"
      >
        <ExportMenu
          reportKey="accounts"
          label={selection.selectAllMatching ? 'Export all matching' : 'Export'}
          filters={exportFiltersFrom(query, ['search', ...USER_FILTER_KEYS])}
          selectedIds={selection.selectAllMatching ? undefined : [...selection.selectedIds]}
        />
      </BulkActionsBar>

      {resend.dialogs}

      <Dialog
        open={pending === 'move'}
        onOpenChange={(open) => (open || busy ? null : setPending(null))}
      >
        <DialogContent size="md">
          <DialogHeader>
            <DialogTitle>Move {who} to a centre</DialogTitle>
            <DialogDescription>
              From their next request they see the new centre&apos;s students, batches and records.
              Students are skipped: they stay at the centre that admitted them.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={(event) => void move(event)} className="space-y-4" noValidate>
            {formError ? <Alert variant="error">{formError}</Alert> : null}
            <Field label="Centre" htmlFor="bulk-branch" error={moveErrors.branch_id} required>
              <Select
                id="bulk-branch"
                data-autofocus
                value={branchId}
                onChange={(event) => setBranchId(event.target.value)}
              >
                <option value="">Choose a centre</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name} ({branch.code})
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Reason"
              htmlFor="bulk-reason"
              error={moveErrors.reason}
              hint="Kept in each account's audit trail."
              required
            >
              <Input
                id="bulk-reason"
                value={reason}
                maxLength={255}
                onChange={(event) => setReason(event.target.value)}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" disabled={busy} onClick={() => setPending(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? 'Moving…' : `Move ${who}`}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <BulkResultDialog
        result={result?.value ?? null}
        title={result?.title ?? ''}
        doneLabel={result?.done ?? ''}
        itemNoun="account"
        onClose={() => setResult(null)}
      />
    </>
  );
}
