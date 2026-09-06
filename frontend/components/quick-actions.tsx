/**
 * A dashboard's short list of "things you probably came here to do" — create
 * a batch, add a student, start an import.
 *
 * Plain buttons/links in a grid, not a menu: the whole point of a dashboard
 * shortcut is that it costs zero clicks to discover and one click to use, so
 * hiding these behind a disclosure would work against the reason they exist.
 */
import type { ReactNode } from 'react';
import Link from 'next/link';

import { formatShortcutLabel } from '@/hooks/use-keyboard-shortcuts';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface QuickAction {
  id: string;
  label: string;
  icon?: ReactNode;
  /** A chord in `use-keyboard-shortcuts` grammar, shown as a hint only — this
   *  component does not register the shortcut itself. */
  shortcut?: string;
  disabled?: boolean;
  href?: string;
  onClick?: () => void;
}

export function QuickActions({ actions, className }: { actions: QuickAction[]; className?: string }) {
  if (actions.length === 0) return null;

  return (
    <div className={cn('grid grid-cols-2 gap-2 sm:grid-cols-3', className)}>
      {actions.map((action) => {
        const content = (
          <>
            {action.icon ? (
              <span aria-hidden="true" className="text-muted-foreground">
                {action.icon}
              </span>
            ) : null}
            <span className="flex-1 text-left">{action.label}</span>
            {action.shortcut ? (
              <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 text-[0.65rem] text-muted-foreground">
                {formatShortcutLabel(action.shortcut)}
              </kbd>
            ) : null}
          </>
        );

        if (action.href && !action.disabled) {
          return (
            <Button key={action.id} asChild variant="outline" className="justify-start gap-2">
              <Link href={action.href}>{content}</Link>
            </Button>
          );
        }

        return (
          <Button
            key={action.id}
            variant="outline"
            className="justify-start gap-2"
            disabled={action.disabled}
            onClick={action.onClick}
          >
            {content}
          </Button>
        );
      })}
    </div>
  );
}
