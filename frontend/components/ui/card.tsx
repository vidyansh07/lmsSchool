import * as React from 'react';

import { cn } from '@/lib/utils';

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        // A white card pressed out of an off-white page. Two opposed shadows do
        // the lifting -- cool below-right, a white highlight above-left -- and
        // the hairline stays under them.
        //
        // The hairline is not decoration here. A card distinguished by shadow
        // alone sits at about 1.2:1 against the page, and `theme-contrast`
        // asks for 3:1 on anything that bounds a control. The shadows give the
        // look; the border keeps it legible for somebody on a dim laptop in a
        // bright room, which is most people most of the time.
        'rounded-card border border-line bg-surface shadow-raised',
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col gap-1 p-4 pb-3', className)} {...props} />;
}

export function CardTitle({
  className,
  as: Comp = 'h3',
  ...props
}: React.HTMLAttributes<HTMLHeadingElement> & { as?: 'h2' | 'h3' }) {
  // Defaults to h3, since a card most often sits inside an h2-labelled
  // section. A page whose first heading-bearing content after its own h1 is
  // a bare top-level Card (no wrapping h2) should pass `as="h2"` instead, so
  // the heading order never skips a level.
  return <Comp className={cn('text-lg font-semibold leading-tight', className)} {...props} />;
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('text-xs text-ink-muted', className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-4 pt-0', className)} {...props} />;
}

export function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex items-center gap-2 p-4 pt-0', className)} {...props} />;
}
