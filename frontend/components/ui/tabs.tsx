'use client';

/**
 * A set of panels sharing one row of labels — no native HTML element covers
 * this, so it follows the WAI-ARIA Tabs pattern by hand: `tablist`/`tab`/
 * `tabpanel` roles, a roving `tabIndex` across the triggers (Tab enters and
 * leaves the row in one stop; Left/Right/Home/End move within it), and
 * "automatic activation" — moving focus with an arrow key switches the
 * panel immediately, rather than requiring a separate Enter. That is the
 * more common convention for tabs specifically (unlike a menu, where
 * moving focus previews nothing until you commit).
 *
 * Only the active panel is ever mounted, not rendered-and-hidden: nothing in
 * this app has asked for a cross-fade between tab panels, and mounting all
 * of them "just in case" would run every panel's data fetching at once.
 */
import * as React from 'react';

import { cn } from '@/lib/utils';

interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
  baseId: string;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabsContext(component: string) {
  const context = React.useContext(TabsContext);
  if (!context) throw new Error(`<${component}> must be rendered inside <Tabs>`);
  return context;
}

function triggerId(baseId: string, value: string) {
  return `${baseId}-trigger-${value}`;
}
function panelId(baseId: string, value: string) {
  return `${baseId}-panel-${value}`;
}

export interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
}

export function Tabs({ value, defaultValue, onValueChange, className, children, ...props }: TabsProps) {
  const baseId = React.useId();
  const [uncontrolled, setUncontrolled] = React.useState(defaultValue ?? '');
  const isControlled = value !== undefined;
  const currentValue = isControlled ? value : uncontrolled;

  const setValue = React.useCallback(
    (next: string) => {
      if (!isControlled) setUncontrolled(next);
      onValueChange?.(next);
    },
    [isControlled, onValueChange],
  );

  return (
    <TabsContext.Provider value={{ value: currentValue, setValue, baseId }}>
      <div className={cn(className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export function TabsList({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const containerRef = React.useRef<HTMLDivElement>(null);

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || !containerRef.current) return;
    event.preventDefault();

    const tabs = Array.from(containerRef.current.querySelectorAll<HTMLElement>('[role="tab"]:not(:disabled)'));
    if (tabs.length === 0) return;

    const currentIndex = tabs.findIndex((tab) => tab === document.activeElement);
    let nextIndex: number;
    if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = tabs.length - 1;
    else if (event.key === 'ArrowRight') nextIndex = currentIndex === -1 ? 0 : (currentIndex + 1) % tabs.length;
    else nextIndex = currentIndex === -1 ? tabs.length - 1 : (currentIndex - 1 + tabs.length) % tabs.length;

    tabs[nextIndex]?.focus();
    tabs[nextIndex]?.click();
  }

  return (
    <div
      ref={containerRef}
      role="tablist"
      onKeyDown={onKeyDown}
      className={cn('inline-flex items-center gap-1 border-b border-border', className)}
      {...props}
    />
  );
}

export interface TabsTriggerProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'value'> {
  value: string;
}

export function TabsTrigger({ value, className, onClick, ...props }: TabsTriggerProps) {
  const { value: active, setValue, baseId } = useTabsContext('TabsTrigger');
  const isActive = active === value;

  return (
    <button
      type="button"
      role="tab"
      id={triggerId(baseId, value)}
      aria-controls={panelId(baseId, value)}
      aria-selected={isActive}
      tabIndex={isActive ? 0 : -1}
      onClick={(event) => {
        setValue(value);
        onClick?.(event);
      }}
      className={cn(
        'relative inline-flex min-h-11 items-center px-3 py-2 text-sm font-medium text-muted-foreground transition-colors', // min-h-11: ≥44px tap target
        'hover:text-foreground disabled:pointer-events-none disabled:opacity-50',
        isActive && 'text-foreground',
        // The active indicator is a bottom border, not a background swap —
        // colour alone would leave a low-vision or colour-blind reader
        // guessing which tab is selected; the line is a second, positional
        // signal that survives the palette.
        isActive && 'after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-primary',
        className,
      )}
      {...props}
    />
  );
}

export interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
}

export function TabsContent({ value, className, ...props }: TabsContentProps) {
  const { value: active, baseId } = useTabsContext('TabsContent');
  if (active !== value) return null;

  return (
    <div
      role="tabpanel"
      id={panelId(baseId, value)}
      aria-labelledby={triggerId(baseId, value)}
      tabIndex={0}
      className={cn('animate-fade-in pt-4 outline-none', className)}
      {...props}
    />
  );
}
