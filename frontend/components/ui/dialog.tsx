'use client';

/**
 * A modal dialog: centred, backdrop-blocked, focus-trapped.
 *
 * Built on a plain `<div role="dialog">`, not the native `<dialog>` element.
 * `<dialog>` looks like the obvious choice — a real element with a modal
 * mode and free focus trapping — but jsdom, this project's test
 * environment, ships `HTMLDialogElement` as a bare stub: no `showModal`, no
 * `close`, no focus containment. Calling `showModal()` would throw in every
 * test in this suite, and catching that and falling back to manual focus
 * management would mean maintaining the trap logic twice regardless. This
 * app already has a proven, tested version of that logic in
 * `components/confirm.tsx`; `hooks/use-focus-trap.ts` is that logic made
 * reusable, and this component is `Confirm` generalised — a labelled title,
 * an optional description, arbitrary body content, and a close affordance,
 * instead of a fixed confirm/cancel shape.
 *
 * No `DialogTrigger`: like `Confirm`, this is fully controlled. Wire any
 * element's `onClick` to flip `open`, and focus still restores correctly on
 * close, because `useFocusTrap` captures `document.activeElement` when the
 * dialog opens rather than depending on a designated trigger ref.
 *
 * Motion pairing, used across every overlay in this file set: an entrance
 * plays one of `globals.css`'s `.animate-*` utilities forward at its
 * built-in duration; the exit plays the *same* keyframe in reverse — which,
 * since each keyframe only declares a `from` state, turns "fade to visible"
 * into "fade to gone" — at the next duration token down (`quick` under
 * `base`, `instant` under `quick`), applied via an inline `animation`
 * shorthand rather than a second utility class. That keeps exits at roughly
 * 60–70% of the matching entrance without inventing a single new duration.
 */
import * as React from 'react';
import { X } from 'lucide-react';
import { cva, type VariantProps } from 'class-variance-authority';

import { useFocusTrap } from '@/hooks/use-focus-trap';
import { usePresence } from '@/hooks/use-presence';
import { cn } from '@/lib/utils';

const EXIT_DURATION_MS = 90; // mirrors --duration-instant, the reverse of .animate-scale-in's --duration-quick

interface DialogContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  titleId: string;
  descriptionId: string;
  hasDescription: boolean;
  setHasDescription: (value: boolean) => void;
}

const DialogContext = React.createContext<DialogContextValue | null>(null);

function useDialogContext(component: string) {
  const context = React.useContext(DialogContext);
  if (!context) throw new Error(`<${component}> must be rendered inside <Dialog>`);
  return context;
}

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}

/** Provides context only — renders no DOM of its own, so `DialogContent` can
 *  sit anywhere inside it without an extra wrapping element in the tree. */
export function Dialog({ open, onOpenChange, children }: DialogProps) {
  const titleId = React.useId();
  const descriptionId = React.useId();
  const [hasDescription, setHasDescription] = React.useState(false);

  return (
    <DialogContext.Provider value={{ open, onOpenChange, titleId, descriptionId, hasDescription, setHasDescription }}>
      {children}
    </DialogContext.Provider>
  );
}

const dialogContentVariants = cva(
  'relative w-full rounded-[var(--radius-card)] border border-border bg-surface p-5 shadow-lg',
  {
    variants: {
      size: {
        sm: 'max-w-sm',
        md: 'max-w-md',
        lg: 'max-w-lg',
      },
    },
    defaultVariants: { size: 'md' },
  },
);

export interface DialogContentProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof dialogContentVariants> {
  /** Hide the built-in top-right close button, e.g. when the footer already offers one. */
  hideCloseButton?: boolean;
}

export function DialogContent({ className, size, hideCloseButton, children, ...props }: DialogContentProps) {
  const { open, onOpenChange, titleId, descriptionId, hasDescription } = useDialogContext('DialogContent');
  const mounted = usePresence(open, EXIT_DURATION_MS);
  const containerRef = useFocusTrap<HTMLDivElement>({ open, onClose: () => onOpenChange(false) });

  if (!mounted) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onMouseDown={(event) => {
        // Not a same-target check (Confirm's simpler version, with a single
        // backdrop element, can get away with that): the tint layer just
        // below is its own element, so a click on it would never equal
        // `currentTarget`. "Outside the panel" is the actual rule.
        if (!containerRef.current?.contains(event.target as Node)) onOpenChange(false);
      }}
    >
      <div
        aria-hidden="true"
        className={cn('absolute inset-0 bg-foreground/40', open ? 'animate-fade-in' : undefined)}
        style={!open ? { animation: 'fade-in var(--duration-quick) var(--ease-out-quick) reverse both' } : undefined}
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={hasDescription ? descriptionId : undefined}
        className={cn(dialogContentVariants({ size }), open ? 'animate-scale-in' : undefined, className)}
        style={
          !open
            ? { animation: `scale-in ${EXIT_DURATION_MS}ms var(--ease-out-quick) reverse both` }
            : undefined
        }
        {...props}
      >
        {hideCloseButton ? null : (
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close"
            className={cn(
              'absolute right-3 top-3 inline-flex size-8 items-center justify-center rounded-md text-muted-foreground',
              'before:absolute before:-inset-2 before:content-[""]', // ≥44px tap target, invisible
              'hover:bg-muted hover:text-foreground',
            )}
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        )}
        {children}
      </div>
    </div>
  );
}

export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mb-4 space-y-1 pr-8', className)} {...props} />;
}

export function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  const { titleId } = useDialogContext('DialogTitle');
  return <h2 id={titleId} className={cn('text-base font-semibold', className)} {...props} />;
}

export function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  const { descriptionId, setHasDescription } = useDialogContext('DialogDescription');
  // An effect, not a render-time call: `setHasDescription` belongs to
  // `Dialog`, an ancestor, and updating another component's state while
  // *this* component renders is unsupported — React only sanctions adjusting
  // a component's own state during its own render. The one-tick delay before
  // `aria-describedby` lands is immaterial; nothing is painted from it.
  React.useEffect(() => {
    setHasDescription(true);
    return () => setHasDescription(false);
  }, [setHasDescription]);
  return <p id={descriptionId} className={cn('text-sm text-muted-foreground', className)} {...props} />;
}

export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mt-5 flex justify-end gap-2', className)} {...props} />;
}

export function DialogClose({ className, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { onOpenChange } = useDialogContext('DialogClose');
  return (
    <button
      type="button"
      onClick={(event) => {
        onClick?.(event);
        onOpenChange(false);
      }}
      className={className}
      {...props}
    />
  );
}
