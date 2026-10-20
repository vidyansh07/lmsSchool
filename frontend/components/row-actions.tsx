'use client';

/**
 * What a person may do to one row, filtered by what they are allowed to do.
 *
 * Every operational screen in this product ends in a table, and until now each
 * table decided for itself what the last column held. Most settled on a single
 * "open" link, so a counsellor who could edit a student still had to open the
 * record to find that out, and a trainer who could not edit one saw the same
 * column and learned nothing. The actions existed; the table never offered
 * them.
 *
 * Three rules hold this together:
 *
 * 1. **An action nobody may perform is not rendered.** Not greyed out — absent.
 *    A disabled control that never becomes enabled is a puzzle, and in a list
 *    of fifty rows it is fifty puzzles. Where a refusal is genuinely useful to
 *    see, `disabledReason` says so in a tooltip and the control stays.
 *
 * 2. **The capability is checked here, and again on the server.** This decides
 *    what to draw. It does not decide what is permitted: hiding a button has
 *    never stopped anybody who can type a URL, and every endpoint behind these
 *    makes its own decision. If the two ever disagree, the server is right.
 *
 * 3. **The first two survivors stay visible; the rest fold into a menu.** Not
 *    the first two listed — the first two *the caller may use*, so a person
 *    with one permission gets one button rather than an overflow menu holding
 *    a single item.
 *
 * A row's actions must not trigger the row's own click. Every control here
 * stops propagation, because a table whose rows open on click is the normal
 * shape in this app and "delete" opening the record instead would be the
 * worst possible miss.
 */
import Link from 'next/link';
import { MoreHorizontal } from 'lucide-react';
import * as React from 'react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { Tooltip } from '@/components/ui/tooltip';
import { useAuth } from '@/components/auth-provider';
import type { CapabilityName } from '@/lib/capabilities';
import { cn } from '@/lib/utils';

export interface RowAction {
  /** What the control says, and its accessible name in the menu. */
  label: string;
  /** The icon for the inline control. The menu shows the label as well. */
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  /**
   * The capability this needs. Omitted means everyone who can see the row may
   * do it — true of "open", and of very little else.
   */
  capability?: CapabilityName;
  /** A link action. Give this or `onSelect`, not both. */
  href?: string;
  /** A button action. */
  onSelect?: () => void;
  /**
   * Marks a destructive action: it is drawn in the danger tone, and sorted to
   * the end of the menu behind a separator so "delete" is never adjacent to
   * the action somebody actually meant.
   */
  destructive?: boolean;
  /**
   * Why this is unavailable *right now*, for a reason that is about this row
   * rather than this person — "already cancelled", "has payments against it".
   * The control stays, disabled, with this as its tooltip. A permission the
   * caller lacks is not one of these: that action is simply absent.
   */
  disabledReason?: string;
}

/** How many actions stay as buttons before the rest fold into the menu. */
const INLINE_LIMIT = 2;

export interface RowActionsProps {
  actions: RowAction[];
  /** Names the row for a screen reader: "Open Asha Rao", not "Open". */
  subject: string;
  className?: string;
}

export function RowActions({ actions, subject, className }: RowActionsProps) {
  const { can } = useAuth();

  // Permission first, order second. A caller with one permission gets one
  // button, not a menu with one thing in it.
  const permitted = actions.filter((action) => !action.capability || can(action.capability));
  if (permitted.length === 0) return null;

  const ordinary = permitted.filter((action) => !action.destructive);
  const destructive = permitted.filter((action) => action.destructive);
  // Destructive actions never take an inline slot: they belong behind the
  // extra deliberate step of opening a menu.
  const inline = ordinary.slice(0, INLINE_LIMIT);
  const folded = [...ordinary.slice(INLINE_LIMIT), ...destructive];

  return (
    <div
      className={cn('flex items-center justify-end gap-0.5', className)}
      // One guard for the whole group, so an action added later cannot forget.
      onClick={(event) => event.stopPropagation()}
    >
      {inline.map((action) => (
        <InlineAction key={action.label} action={action} subject={subject} />
      ))}
      {folded.length > 0 ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="size-8 p-0 text-ink-muted"
              aria-label={`More actions for ${subject}`}
            >
              <MoreHorizontal className="size-4" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {folded.map((action, index) => {
              const isFirstDestructive =
                action.destructive === true && folded[index - 1]?.destructive !== true;
              return (
                <React.Fragment key={action.label}>
                  {isFirstDestructive && index > 0 ? <DropdownMenuSeparator /> : null}
                  <DropdownMenuItem
                    destructive={action.destructive}
                    disabled={Boolean(action.disabledReason)}
                    title={action.disabledReason}
                    onSelect={() => {
                      if (action.disabledReason) return;
                      if (action.href) {
                        window.location.href = action.href;
                        return;
                      }
                      action.onSelect?.();
                    }}
                  >
                    <action.icon className="size-4" aria-hidden={true} />
                    {action.label}
                  </DropdownMenuItem>
                </React.Fragment>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  );
}

function InlineAction({ action, subject }: { action: RowAction; subject: string }) {
  const label = `${action.label} ${subject}`;
  const Icon = action.icon;

  if (action.disabledReason) {
    return (
      <Tooltip content={action.disabledReason}>
        {/* A disabled button takes no pointer events, so the tooltip needs a
            wrapper that still receives them. */}
        <span className="inline-flex">
          <Button
            variant="ghost"
            size="sm"
            disabled
            className="size-8 p-0 text-ink-muted"
            aria-label={label}
          >
            <Icon className="size-4" aria-hidden={true} />
          </Button>
        </span>
      </Tooltip>
    );
  }

  return (
    <Tooltip content={action.label}>
      {action.href ? (
        <Button asChild variant="ghost" size="sm" className="size-8 p-0 text-ink-muted">
          <Link href={action.href} aria-label={label}>
            <Icon className="size-4" aria-hidden={true} />
          </Link>
        </Button>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          className="size-8 p-0 text-ink-muted"
          aria-label={label}
          onClick={action.onSelect}
        >
          <Icon className="size-4" aria-hidden={true} />
        </Button>
      )}
    </Tooltip>
  );
}
