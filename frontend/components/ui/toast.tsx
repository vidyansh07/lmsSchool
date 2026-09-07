'use client';

/**
 * A transient, corner-anchored notification: "Batch created", "Export
 * failed" — feedback for an action just taken, not a thing blocking the
 * screen (that is `Dialog`, or for anything irreversible, `components/confirm.tsx`).
 *
 * `usePresence` doesn't fit here — it tracks one boolean's mount lifecycle,
 * and a toast stack is a *list* whose members come and go independently.
 * Dismissal is two-phase instead: `dismissToast` immediately flags a toast
 * `closing` (which switches its animation to the reverse-exit and stops it
 * blocking new toasts from stacking above it), then removes it from state
 * `EXIT_DURATION_MS` later, once that animation has actually played.
 *
 * One `aria-live="polite"` region on the container announces every toast as
 * it is added; individual toasts don't carry their own `role="status"`,
 * which would register a second, overlapping live region and risk being
 * announced twice by the same change.
 *
 * Provider, hook and `Toaster` are all exported from here, but none of them
 * are mounted anywhere — `app/layout.tsx` and `components/app-shell.tsx` are
 * both out of this task's reach, and mounting `<ToastProvider>` /
 * `<Toaster />` belongs in whichever of those actually owns the shell.
 * `useToast()` throws a clear error if called before that wiring exists,
 * rather than silently doing nothing.
 */
import * as React from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';

import { cn } from '@/lib/utils';

export type ToastVariant = 'info' | 'success' | 'warning' | 'error';

export interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
  /** Auto-dismiss after this many milliseconds. Defaults to 5000; pass `0` to require manual dismissal. */
  durationMs?: number;
}

interface ToastRecord extends Required<Omit<ToastOptions, 'durationMs'>> {
  id: string;
  closing: boolean;
}

interface ToastContextValue {
  toasts: ToastRecord[];
  addToast: (options: ToastOptions) => string;
  dismissToast: (id: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION_MS = 5000;
const EXIT_DURATION_MS = 150; // mirrors --duration-quick, the reverse of slide-in-right's --duration-base entrance

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastRecord[]>([]);
  const idPrefix = React.useId();
  const nextIndex = React.useRef(0);
  const timers = React.useRef(new Map<string, ReturnType<typeof setTimeout>>());

  React.useEffect(() => {
    const activeTimers = timers.current;
    return () => {
      activeTimers.forEach((timer) => clearTimeout(timer));
      activeTimers.clear();
    };
  }, []);

  const dismissToast = React.useCallback((id: string) => {
    setToasts((current) => current.map((toast) => (toast.id === id ? { ...toast, closing: true } : toast)));
    const removeTimer = setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
      timers.current.delete(id);
    }, EXIT_DURATION_MS);
    timers.current.set(id, removeTimer);
  }, []);

  const addToast = React.useCallback(
    (options: ToastOptions) => {
      const id = `${idPrefix}-${nextIndex.current++}`;
      setToasts((current) => [
        ...current,
        {
          id,
          title: options.title,
          description: options.description ?? '',
          variant: options.variant ?? 'info',
          closing: false,
        },
      ]);

      const durationMs = options.durationMs ?? DEFAULT_DURATION_MS;
      if (durationMs > 0) {
        const hideTimer = setTimeout(() => dismissToast(id), durationMs);
        timers.current.set(`${id}-hide`, hideTimer);
      }
      return id;
    },
    [idPrefix, dismissToast],
  );

  return (
    <ToastContext.Provider value={{ toasts, addToast, dismissToast }}>{children}</ToastContext.Provider>
  );
}

function useToastContext(component: string) {
  const context = React.useContext(ToastContext);
  if (!context) throw new Error(`${component} must be used inside <ToastProvider>`);
  return context;
}

/** `toast(...)` returns the new toast's id, so a caller can `dismiss` it
 *  early — e.g. once a background upload it was reporting on completes. */
export function useToast() {
  const { addToast, dismissToast } = useToastContext('useToast()');
  return { toast: addToast, dismiss: dismissToast };
}

const VARIANT_ICON: Record<ToastVariant, React.ComponentType<React.SVGProps<SVGSVGElement>>> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

const VARIANT_ICON_CLASS: Record<ToastVariant, string> = {
  info: 'text-muted-foreground',
  success: 'text-success',
  warning: 'text-warning',
  error: 'text-destructive',
};

function ToastItem({ toast, onDismiss }: { toast: ToastRecord; onDismiss: () => void }) {
  const Icon = VARIANT_ICON[toast.variant];

  return (
    <div
      className={cn(
        'pointer-events-auto flex w-full items-start gap-3 rounded-[var(--radius-card)] border border-border bg-surface p-4 shadow-lg',
        !toast.closing && 'animate-slide-in-right',
      )}
      style={
        toast.closing
          ? { animation: `slide-in-right ${EXIT_DURATION_MS}ms var(--ease-out-quick) reverse both` }
          : undefined
      }
    >
      <Icon className={cn('mt-0.5 size-4 shrink-0', VARIANT_ICON_CLASS[toast.variant])} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description ? <p className="mt-0.5 text-xs text-muted-foreground">{toast.description}</p> : null}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className={cn(
          'relative inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground',
          'before:absolute before:-inset-2.5 before:content-[""]', // ≥44px tap target, invisible
          'hover:bg-muted hover:text-foreground',
        )}
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

/** Renders the toast stack. Mount exactly one of these, anywhere inside `ToastProvider`. */
export function Toaster() {
  const { toasts, dismissToast } = useToastContext('<Toaster>');

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => dismissToast(toast.id)} />
      ))}
    </div>
  );
}
