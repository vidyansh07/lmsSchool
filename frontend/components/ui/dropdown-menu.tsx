'use client';

/**
 * A button-triggered menu of actions — the "⋯" on a table row, a bulk-action
 * picker, anything that used to be a row of buttons squeezed too tight.
 *
 * Hand-rolled with `absolute` positioning inside a `relative` wrapper rather
 * than measuring the trigger's position with `getBoundingClientRect` and
 * placing the panel with `fixed` coordinates: this app's menus open from a
 * fixed toolbar or a table row, never near a viewport edge that would need
 * flip/shift collision handling, so the anchored-wrapper approach gets the
 * same result for every real call site without a from-scratch Popper.
 *
 * Items are real `<button>`s, so Enter and Space activate the focused one
 * natively — the only keyboard behaviour this file adds is Up/Down/Home/End
 * to move a roving `tabIndex` between them, the same roving pattern
 * `data-table.tsx` uses for its rows. Dismissal (outside click, Escape,
 * focus return) comes from `hooks/use-dismissable-layer.ts`, shared with
 * `popover.tsx` — a menu is not modal, so nothing here traps Tab or locks
 * scroll the way `Dialog` does.
 */
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';

import { useDismissableLayer } from '@/hooks/use-dismissable-layer';
import { usePresence } from '@/hooks/use-presence';
import { cn } from '@/lib/utils';

const EXIT_DURATION_MS = 90; // mirrors --duration-instant, the reverse of .animate-scale-in's --duration-quick

interface DropdownMenuContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLElement | null>;
}

const DropdownMenuContext = React.createContext<DropdownMenuContextValue | null>(null);

function useDropdownMenuContext(component: string) {
  const context = React.useContext(DropdownMenuContext);
  if (!context) throw new Error(`<${component}> must be rendered inside <DropdownMenu>`);
  return context;
}

export interface DropdownMenuProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function DropdownMenu({ open, onOpenChange, defaultOpen = false, children, className }: DropdownMenuProps) {
  const [uncontrolled, setUncontrolled] = React.useState(defaultOpen);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : uncontrolled;
  const triggerRef = React.useRef<HTMLElement | null>(null);

  const setOpen = React.useCallback(
    (next: boolean) => {
      if (!isControlled) setUncontrolled(next);
      onOpenChange?.(next);
    },
    [isControlled, onOpenChange],
  );

  return (
    <DropdownMenuContext.Provider value={{ open: isOpen, setOpen, triggerRef }}>
      <div className={cn('relative inline-block', className)}>{children}</div>
    </DropdownMenuContext.Provider>
  );
}

export interface DropdownMenuTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Render the child element instead of a <button>, keeping the styles — see `Button`. */
  asChild?: boolean;
}

export function DropdownMenuTrigger({ asChild, onClick, children, ...props }: DropdownMenuTriggerProps) {
  const { open, setOpen, triggerRef } = useDropdownMenuContext('DropdownMenuTrigger');
  const Component = asChild ? Slot : 'button';

  return (
    <Component
      // `Component` is a union of `Slot` and the `'button'` intrinsic, so its
      // ref type resolves to `HTMLButtonElement` specifically; `triggerRef`
      // is typed for either case in the shared context (it also anchors a
      // `Slot`-rendered child, which can be any element) — safe to narrow.
      ref={triggerRef as React.Ref<HTMLButtonElement>}
      type={asChild ? undefined : 'button'}
      aria-haspopup="menu"
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

export function DropdownMenuContent({
  className,
  align = 'start',
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { align?: 'start' | 'end' }) {
  const { open, setOpen, triggerRef } = useDropdownMenuContext('DropdownMenuContent');
  const mounted = usePresence(open, EXIT_DURATION_MS);
  const containerRef = useDismissableLayer<HTMLDivElement>({ open, onClose: () => setOpen(false), triggerRef });

  React.useEffect(() => {
    if (!open || !containerRef.current) return;
    containerRef.current.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus();
  }, [open, containerRef]);

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || !containerRef.current) return;
    event.preventDefault();

    const items = Array.from(
      containerRef.current.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])'),
    );
    if (items.length === 0) return;

    const currentIndex = items.findIndex((item) => item === document.activeElement);
    let nextIndex: number;
    if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = items.length - 1;
    else if (event.key === 'ArrowDown') nextIndex = currentIndex === -1 ? 0 : (currentIndex + 1) % items.length;
    else nextIndex = currentIndex === -1 ? items.length - 1 : (currentIndex - 1 + items.length) % items.length;

    items[nextIndex]?.focus();
  }

  if (!mounted) return null;

  return (
    <div
      ref={containerRef}
      role="menu"
      onKeyDown={onKeyDown}
      className={cn(
        'absolute z-40 mt-1 min-w-[10rem] rounded-md border border-border bg-surface p-1 shadow-lg',
        align === 'end' ? 'right-0' : 'left-0',
        open ? 'animate-scale-in' : undefined,
        align === 'end' ? 'origin-top-right' : 'origin-top-left',
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

export interface DropdownMenuItemProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  onSelect?: () => void;
  destructive?: boolean;
}

export function DropdownMenuItem({ className, onSelect, onClick, destructive, ...props }: DropdownMenuItemProps) {
  const { setOpen, triggerRef } = useDropdownMenuContext('DropdownMenuItem');

  return (
    <button
      type="button"
      role="menuitem"
      tabIndex={-1}
      onClick={(event) => {
        onClick?.(event);
        onSelect?.();
        setOpen(false);
        // Unlike an outside click, which should leave focus wherever the
        // person clicked, choosing an item removes the whole menu — focus
        // has to go somewhere, and the trigger that opened it is the one
        // place guaranteed to still be there.
        triggerRef.current?.focus();
      }}
      className={cn(
        'flex min-h-11 w-full items-center gap-2 rounded-sm px-2.5 py-2 text-left text-sm', // min-h-11: ≥44px tap target
        'hover:bg-muted focus-visible:bg-muted focus-visible:outline-none',
        'disabled:pointer-events-none disabled:opacity-50',
        destructive ? 'text-destructive' : 'text-foreground',
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuLabel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('px-2.5 py-1.5 text-xs font-medium text-muted-foreground', className)} {...props} />
  );
}

export function DropdownMenuSeparator({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div role="separator" className={cn('my-1 h-px bg-border', className)} {...props} />;
}
