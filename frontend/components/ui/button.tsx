import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

/**
 * One filled button per screen, everything else an outline.
 *
 * That is the rule the variants are shaped around: `primary` is the single
 * action a screen is asking for, and a toolbar of five equally loud buttons
 * tells a reader nothing about which one they came to press. `secondary` and
 * `outline` are the same weight on purpose — both read as available rather
 * than as recommended.
 *
 * `hover` darkens the token rather than dropping opacity. A button at 90%
 * opacity over a hairline border lets the border show through the fill,
 * which is visible as a faint outline inside the button on hover.
 */
const buttonVariants = cva(
  'relative inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control text-xs font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action',
  {
    variants: {
      variant: {
        primary: 'bg-action text-action-fg hover:bg-action-hover',
        secondary: 'bg-sunken text-ink hover:bg-line',
        outline: 'border border-line bg-surface text-ink hover:border-line-strong hover:bg-sunken',
        ghost: 'bg-transparent text-ink hover:bg-sunken',
        destructive: 'bg-danger text-danger-fg hover:brightness-90',
      },
      size: {
        // The visible box stays compact — this is a dense operations tool and a
        // toolbar of 44px buttons pushes the table off the screen. The *hit*
        // area is expanded to 44px with a centred pseudo-element instead, so a
        // finger gets the target the guidelines ask for without the layout
        // paying for it. `relative` is on the base class for this reason.
        sm: "h-8 px-2.5 text-2xs before:absolute before:left-0 before:right-0 before:top-1/2 before:h-11 before:-translate-y-1/2 before:content-['']",
        md: "h-9 px-3.5 before:absolute before:left-0 before:right-0 before:top-1/2 before:h-11 before:-translate-y-1/2 before:content-['']",
        lg: 'h-11 px-5 text-sm',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Render the child element instead of a <button>, keeping the styles. */
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Component = asChild ? Slot : 'button';
  return (
    <Component className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}

export { buttonVariants };
