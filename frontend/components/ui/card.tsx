import * as React from 'react';

import { cn } from '@/lib/utils';

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        // A white card on a white page: the hairline draws the edge and the
        // shadow lifts it. Neither is heavy on its own, and together they do
        // the job a grey page used to.
        'rounded-card border border-border bg-surface',
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col gap-1 p-5 pb-3', className)} {...props} />;
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
  return <Comp className={cn('text-base font-semibold leading-tight', className)} {...props} />;
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('text-sm text-muted-foreground', className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-5 pt-0', className)} {...props} />;
}

export function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex items-center gap-2 p-5 pt-0', className)} {...props} />;
}
