import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'press relative inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
  {
    variants: {
      variant: {
        primary: 'bg-primary text-primary-foreground hover:opacity-90',
        secondary: 'bg-muted text-foreground hover:bg-accent',
        outline: 'border border-border bg-transparent hover:bg-muted',
        ghost: 'bg-transparent hover:bg-muted',
        destructive: 'bg-destructive text-destructive-foreground hover:opacity-90',
      },
      size: {
        // The visible box stays compact — this is a dense operations tool and a
        // toolbar of 44px buttons pushes the table off the screen. The *hit*
        // area is expanded to 44px with a centred pseudo-element instead, so a
        // finger gets the target the guidelines ask for without the layout
        // paying for it. `relative` is on the base class for this reason.
        sm: "h-8 px-3 text-xs before:absolute before:left-0 before:right-0 before:top-1/2 before:h-11 before:-translate-y-1/2 before:content-['']",
        md: "h-10 px-4 before:absolute before:left-0 before:right-0 before:top-1/2 before:h-11 before:-translate-y-1/2 before:content-['']",
        lg: 'h-11 px-6 text-base',
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
