'use client';

/**
 * "Resend invitations" for a selection bar: confirm, send, show who was
 * skipped and why. Shared by the accounts list and the trainers hub, which
 * differ only in which endpoint resolves their rows.
 */

import { useState } from 'react';

import { BulkResultDialog } from '@/components/bulk-result-dialog';
import { Confirm } from '@/components/confirm';
import { useToast } from '@/components/ui/toast';
import { errorMessage } from '@/lib/api';
import type { BulkResult } from '@/lib/bulk';
import { formatCount } from '@/lib/format';

export function useResendInvitations({
  count,
  itemNoun,
  send,
  onDone,
}: {
  count: number;
  itemNoun: string;
  send: () => Promise<BulkResult>;
  onDone: () => void;
}) {
  const { toast } = useToast();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BulkResult | null>(null);

  async function run() {
    setBusy(true);
    try {
      setResult(await send());
      onDone();
    } catch (cause) {
      toast({
        title: 'Could not send the invitations',
        description: errorMessage(cause),
        variant: 'error',
      });
    } finally {
      setBusy(false);
      setAsking(false);
    }
  }

  const dialogs = (
    <>
      <Confirm
        open={asking}
        title={`Resend invitations to ${formatCount(count, itemNoun)}?`}
        description="Each gets a new link to set their password. Anyone who already accepted, or whose account is inactive, is skipped and listed."
        confirmLabel="Send invitations"
        confirmVariant="primary"
        isConfirming={busy}
        onConfirm={() => void run()}
        onCancel={() => setAsking(false)}
      />
      <BulkResultDialog
        result={result}
        title="Invitations"
        doneLabel="invited again"
        itemNoun={itemNoun}
        onClose={() => setResult(null)}
      />
    </>
  );

  return { open: () => setAsking(true), dialogs };
}
