'use client';

/**
 * A row of status buttons where every press is confirmed first.
 *
 * Activating, deactivating, archiving or cancelling a course or a batch is a
 * decision with consequences for other people — students lose access, a
 * catalogue entry disappears, enrolments are cancelled. A counsellor should
 * never be one stray click away from any of them, so each action opens a
 * dialog that says in plain words what will happen and asks again. The
 * server still owns the transition table and re-checks every request; this
 * only decides what is offered and what is said before it is sent.
 */
import { useState } from 'react';

import { Confirm } from '@/components/confirm';
import { Button, type ButtonProps } from '@/components/ui/button';

export interface StatusAction<T extends string> {
  target: T;
  /** The button's label: a verb — "Activate", "Archive". */
  label: string;
  /** The dialog's title, as a question. Defaults to `${label}?`. */
  title?: string;
  /** What will happen, in one or two plain sentences. Required: the point of the dialog. */
  description: string;
  /** The confirming button's label. Defaults to `label`. */
  confirmLabel?: string;
  cancelLabel?: string;
  /** `primary` for the one forward action, `destructive` for the ones that take something away. */
  variant?: ButtonProps['variant'];
}

export function StatusActions<T extends string>({
  actions,
  onConfirm,
  busy = false,
  emptyText = 'No status changes are available.',
}: {
  actions: StatusAction<T>[];
  onConfirm: (target: T) => Promise<void> | void;
  busy?: boolean;
  emptyText?: string;
}) {
  const [pending, setPending] = useState<StatusAction<T> | null>(null);
  const [confirming, setConfirming] = useState(false);

  async function confirm() {
    if (!pending) return;
    setConfirming(true);
    try {
      await onConfirm(pending.target);
      setPending(null);
    } finally {
      setConfirming(false);
    }
  }

  if (actions.length === 0) return <p className="text-sm text-ink-muted">{emptyText}</p>;

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <Button
            key={action.target}
            size="sm"
            variant={action.variant ?? 'outline'}
            disabled={busy || confirming}
            onClick={() => setPending(action)}
          >
            {action.label}
          </Button>
        ))}
      </div>
      <Confirm
        open={pending !== null}
        title={pending?.title ?? `${pending?.label ?? ''}?`}
        description={pending?.description}
        confirmLabel={pending?.confirmLabel ?? pending?.label}
        cancelLabel={pending?.cancelLabel ?? 'Go back'}
        confirmVariant={pending?.variant === 'primary' ? 'primary' : (pending?.variant ?? 'destructive')}
        isConfirming={confirming}
        onConfirm={() => void confirm()}
        onCancel={() => (confirming ? null : setPending(null))}
      />
    </>
  );
}
