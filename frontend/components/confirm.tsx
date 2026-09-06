'use client';

/**
 * A confirmation dialog — for irreversible actions ONLY.
 *
 * Do not use this for anything that can be undone or corrected on the next
 * screen: deactivating a user, unpublishing a course, clearing a filter, even
 * most deletes that soft-delete under the hood. The brief for this app is
 * explicit that confirmation dialogs should be minimal and rare — every one
 * that appears for a reversible action trains people to click through them
 * without reading, which is exactly the moment a *real* irreversible one
 * needs their attention. Reserve it for: permanently deleting data, sending
 * something to someone (an email, a certificate) that cannot be unsent, or
 * an action the backend genuinely cannot roll back.
 *
 * Traps focus while open (Tab cycles inside the dialog, Escape closes it) and
 * restores focus to whatever triggered it on close — the same contract every
 * dialog in this app must honour.
 */
import { useEffect, useId, useRef } from 'react';

import { Button, type ButtonProps } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface ConfirmProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Defaults to `destructive` — this dialog exists for actions that warrant it. */
  confirmVariant?: ButtonProps['variant'];
  isConfirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function Confirm({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmVariant = 'destructive',
  isConfirming = false,
  onConfirm,
  onCancel,
}: ConfirmProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    // The cancel button, not confirm: an irreversible action should never be
    // the thing a stray Enter key press lands on. Selected by attribute
    // rather than a ref forwarded through `Button` — that component is a
    // plain function, not `forwardRef`, so its DOM node is not reliably
    // reachable from outside.
    dialogRef.current?.querySelector<HTMLElement>('[data-confirm-cancel]')?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;

      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) return;
      const first = focusable[0] as HTMLElement;
      const last = focusable[focusable.length - 1] as HTMLElement;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previouslyFocused.current?.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className={cn('w-full max-w-sm rounded-[var(--radius-card)] border border-border bg-surface p-5 shadow-lg')}
      >
        <h2 id={titleId} className="text-base font-semibold">
          {title}
        </h2>
        {description ? (
          <p id={descriptionId} className="mt-2 text-sm text-muted-foreground">
            {description}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            data-confirm-cancel
            variant="outline"
            size="sm"
            onClick={onCancel}
            disabled={isConfirming}
          >
            {cancelLabel}
          </Button>
          <Button variant={confirmVariant} size="sm" onClick={onConfirm} disabled={isConfirming}>
            {isConfirming ? 'Working…' : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
