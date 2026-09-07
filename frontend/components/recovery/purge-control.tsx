'use client';

/**
 * The one irreversible control in this app that is not gated by role alone.
 *
 * Three separate things stand between a click and an actual destruction, on
 * purpose: the control is entirely absent without `record.purge` (not
 * disabled — absent, so its existence is never a hint to someone who cannot
 * use it); opening it demands a typed, non-blank reason before the
 * destructive button will even enable, because `PurgeSerializer.reason`
 * refuses a blank one server-side and a form that lets you discover that only
 * after submitting is a worse version of the same rule; and the destructive
 * button itself only opens `Confirm` — reused exactly as built, never a
 * second dialog — rather than acting immediately. Restoring a record next to
 * this one is a single click for a reason: routine, reversible actions
 * earning a confirmation dialog is what trains people to stop reading them.
 *
 * Failure surfaces inline, under the reason field, rather than inside
 * `Confirm` itself — that component has no slot for a message, by design
 * (see its own docstring), so this closes the dialog and keeps the typed
 * reason in place rather than losing it on a failed attempt.
 */
import { useState } from 'react';
import { Flame } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { Confirm } from '@/components/confirm';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/input';
import { errorMessage } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { purgeRecord, type DeletedRecord } from '@/lib/recovery';

export function PurgeControl({ record, onPurged }: { record: DeletedRecord; onPurged: () => void }) {
  const { can } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [isPurging, setIsPurging] = useState(false);
  const [error, setError] = useState('');

  // Not `disabled` — absent. See the module docstring for why.
  if (!can(Capability.recordPurge)) return null;

  function close() {
    setIsOpen(false);
    setReason('');
    setError('');
  }

  async function confirmPurge() {
    setIsPurging(true);
    try {
      await purgeRecord(record.label, record.id, reason.trim());
      setIsConfirmOpen(false);
      close();
      onPurged();
    } catch (cause) {
      setIsConfirmOpen(false);
      setError(errorMessage(cause, 'Could not destroy this record.'));
    } finally {
      setIsPurging(false);
    }
  }

  if (!isOpen) {
    return (
      <Button type="button" variant="destructive" size="sm" onClick={() => setIsOpen(true)}>
        <Flame className="size-3.5" aria-hidden="true" />
        Purge…
      </Button>
    );
  }

  return (
    <div className="w-56 space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
      <label htmlFor={`purge-reason-${record.id}`} className="block text-xs font-medium">
        Why destroy this permanently?
      </label>
      <Textarea
        id={`purge-reason-${record.id}`}
        rows={2}
        className="text-xs"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Required — this cannot be undone."
      />
      {error ? (
        <Alert variant="error" className="p-2 text-xs">
          {error}
        </Alert>
      ) : null}
      <div className="flex gap-1.5">
        <Button
          type="button"
          variant="destructive"
          size="sm"
          disabled={!reason.trim()}
          onClick={() => setIsConfirmOpen(true)}
        >
          Destroy permanently
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={close}>
          Cancel
        </Button>
      </div>

      <Confirm
        open={isConfirmOpen}
        title="Destroy this record permanently?"
        description={`"${record.describes}" will be gone for good, along with the reason you just gave. This cannot be undone.`}
        confirmLabel="Destroy permanently"
        isConfirming={isPurging}
        onConfirm={() => void confirmPurge()}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
