'use client';

/**
 * An edge-anchored panel for a task that wants more room than a dropdown but
 * should not steal the whole screen the way `Dialog` deliberately does — a
 * row's full detail, a filter builder, a multi-field form entered without
 * leaving the list behind it.
 *
 * Shares `useFocusTrap`/`usePresence` with `dialog.tsx` rather than sharing
 * markup with it: a sheet's chrome — edge-anchored, full height, slides
 * rather than pops — is different enough from a centred dialog that forcing
 * one component to render both shapes would leave every size/position prop
 * fighting the others. Two small components sharing the two hooks that
 * actually repeat is a better seam than one component trying to be both.
 *
 * Right edge only: `globals.css` defines a `slide-in-right` keyframe and no
 * mirrored `slide-in-left`, and this file cannot add one. Every panel this
 * app has needed so far opens from the right, so that is the one shape this
 * component offers rather than a `side` prop with a single legal value.
 *
 * See `dialog.tsx` for the entrance/exit duration pairing this reuses.
 */
import * as React from 'react';
import { X } from 'lucide-react';
import { cva, type VariantProps } from 'class-variance-authority';

import { useFocusTrap } from '@/hooks/use-focus-trap';
import { usePresence } from '@/hooks/use-presence';
import { cn } from '@/lib/utils';

const EXIT_DURATION_MS = 150; // mirrors --duration-quick, the reverse of the --duration-base entrance

interface SheetContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  titleId: string;
  descriptionId: string;
  hasDescription: boolean;
  setHasDescription: (value: boolean) => void;
}

const SheetContext = React.createContext<SheetContextValue | null>(null);

function useSheetContext(component: string) {
  const context = React.useContext(SheetContext);
  if (!context) throw new Error(`<${component}> must be rendered inside <Sheet>`);
  return context;
}

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}

export function Sheet({ open, onOpenChange, children }: SheetProps) {
  const titleId = React.useId();
  const descriptionId = React.useId();
  const [hasDescription, setHasDescription] = React.useState(false);

  return (
    <SheetContext.Provider value={{ open, onOpenChange, titleId, descriptionId, hasDescription, setHasDescription }}>
      {children}
    </SheetContext.Provider>
  );
}

const sheetContentVariants = cva(
  'fixed inset-y-0 right-0 z-50 flex h-full w-full flex-col border-l border-border bg-surface p-5 shadow-lg',
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

export interface SheetContentProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof sheetContentVariants> {
  hideCloseButton?: boolean;
}

export function SheetContent({ className, size, hideCloseButton, children, ...props }: SheetContentProps) {
  const { open, onOpenChange, titleId, descriptionId, hasDescription } = useSheetContext('SheetContent');
  const mounted = usePresence(open, EXIT_DURATION_MS);
  const containerRef = useFocusTrap<HTMLDivElement>({ open, onClose: () => onOpenChange(false) });

  if (!mounted) return null;

  return (
    <>
      <div
        aria-hidden="true"
        className={cn('fixed inset-0 z-50 bg-foreground/40', open ? 'animate-fade-in' : undefined)}
        style={
          !open ? { animation: 'fade-in var(--duration-quick) var(--ease-out-quick) reverse both' } : undefined
        }
        onMouseDown={() => onOpenChange(false)}
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={hasDescription ? descriptionId : undefined}
        className={cn(sheetContentVariants({ size }), open ? 'animate-slide-in-right' : undefined, className)}
        style={
          !open
            ? { animation: `slide-in-right ${EXIT_DURATION_MS}ms var(--ease-out-quick) reverse both` }
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
    </>
  );
}

export function SheetHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mb-4 space-y-1 pr-8', className)} {...props} />;
}

export function SheetTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  const { titleId } = useSheetContext('SheetTitle');
  return <h2 id={titleId} className={cn('text-base font-semibold', className)} {...props} />;
}

export function SheetDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  const { descriptionId, setHasDescription } = useSheetContext('SheetDescription');
  React.useEffect(() => {
    setHasDescription(true);
    return () => setHasDescription(false);
  }, [setHasDescription]);
  return <p id={descriptionId} className={cn('text-sm text-muted-foreground', className)} {...props} />;
}

export function SheetFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mt-auto flex justify-end gap-2 pt-5', className)} {...props} />;
}

export function SheetClose({ className, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { onOpenChange } = useSheetContext('SheetClose');
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
