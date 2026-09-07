'use client';

/**
 * A trigger-anchored panel of arbitrary content — a filter builder, a colour
 * picker, a small form — that is not a menu (no `menuitem` semantics, no
 * arrow-key roving) and not modal (no focus trap, no scroll lock).
 *
 * Positioning and dismissal are identical to `dropdown-menu.tsx` — same
 * relative-wrapper anchoring, same `useDismissableLayer` — because the two
 * are the same interaction shape (a floating layer anchored to a trigger)
 * wearing different content rules. No explicit ARIA role is imposed on the
 * content: unlike a menu, what a popover contains varies too much for one
 * role to fit (a form, a note, a preview), so this stays a plain labelled
 * region and focus lands on the panel itself (`tabIndex={-1}`) rather than
 * assuming there is a first focusable child worth jumping to.
 */
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';

import { useDismissableLayer } from '@/hooks/use-dismissable-layer';
import { usePresence } from '@/hooks/use-presence';
import { cn } from '@/lib/utils';

const EXIT_DURATION_MS = 90; // mirrors --duration-instant, the reverse of .animate-scale-in's --duration-quick

interface PopoverContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLElement | null>;
  labelId: string;
}

const PopoverContext = React.createContext<PopoverContextValue | null>(null);

function usePopoverContext(component: string) {
  const context = React.useContext(PopoverContext);
  if (!context) throw new Error(`<${component}> must be rendered inside <Popover>`);
  return context;
}

export interface PopoverProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function Popover({ open, onOpenChange, defaultOpen = false, children, className }: PopoverProps) {
  const [uncontrolled, setUncontrolled] = React.useState(defaultOpen);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : uncontrolled;
  const triggerRef = React.useRef<HTMLElement | null>(null);
  const labelId = React.useId();

  const setOpen = React.useCallback(
    (next: boolean) => {
      if (!isControlled) setUncontrolled(next);
      onOpenChange?.(next);
    },
    [isControlled, onOpenChange],
  );

  return (
    <PopoverContext.Provider value={{ open: isOpen, setOpen, triggerRef, labelId }}>
      <div className={cn('relative inline-block', className)}>{children}</div>
    </PopoverContext.Provider>
  );
}

export interface PopoverTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Render the child element instead of a <button>, keeping the styles — see `Button`. */
  asChild?: boolean;
}

export function PopoverTrigger({ asChild, onClick, children, ...props }: PopoverTriggerProps) {
  const { open, setOpen, triggerRef } = usePopoverContext('PopoverTrigger');
  const Component = asChild ? Slot : 'button';

  return (
    <Component
      // See the identical cast in dropdown-menu.tsx's DropdownMenuTrigger.
      ref={triggerRef as React.Ref<HTMLButtonElement>}
      type={asChild ? undefined : 'button'}
      aria-haspopup="dialog"
      aria-expanded={open}
      onClick={(event: React.MouseEvent<HTMLButtonElement>) => {
        setOpen(!open);
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </Component>
  );
}

export function PopoverContent({
  className,
  align = 'start',
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { align?: 'start' | 'end' }) {
  const { open, setOpen, triggerRef, labelId } = usePopoverContext('PopoverContent');
  const mounted = usePresence(open, EXIT_DURATION_MS);
  const containerRef = useDismissableLayer<HTMLDivElement>({ open, onClose: () => setOpen(false), triggerRef });

  React.useEffect(() => {
    if (open) containerRef.current?.focus();
  }, [open, containerRef]);

  if (!mounted) return null;

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      aria-labelledby={labelId}
      className={cn(
        'absolute z-40 mt-1 w-72 rounded-md border border-border bg-surface p-4 shadow-lg outline-none',
        align === 'end' ? 'right-0 origin-top-right' : 'left-0 origin-top-left',
        open ? 'animate-scale-in' : undefined,
        className,
      )}
      style={
        !open
          ? { animation: `scale-in ${EXIT_DURATION_MS}ms var(--ease-out-quick) reverse both` }
          : undefined
      }
      {...props}
    >
      {children}
    </div>
  );
}

/** Optional heading; wires its id to the panel's `aria-labelledby`. Omit it
 *  for a popover with no natural title and give the trigger its own
 *  `aria-label` instead. */
export function PopoverHeading({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  const { labelId } = usePopoverContext('PopoverHeading');
  return <h3 id={labelId} className={cn('mb-2 text-sm font-semibold', className)} {...props} />;
}
