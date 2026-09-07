'use client';

/**
 * A person's photo, falling back to initials (or a caller-supplied icon) when
 * there is no photo or it fails to load.
 *
 * `AvatarImage` and `AvatarFallback` both need to know whether the image has
 * loaded, failed, or hasn't resolved yet, so `Avatar` holds that in context
 * rather than each tracking its own copy — the two have to agree, or a
 * broken photo would render on top of its own fallback instead of instead
 * of it. Fallback is shown by default (status starts `'loading'` rather than
 * `'idle'`) so a slow image never flashes blank before its `onError` — or
 * its opposite, an empty circle — fires.
 */
import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

type ImageStatus = 'loading' | 'loaded' | 'error';

const AvatarContext = React.createContext<{
  status: ImageStatus;
  setStatus: (status: ImageStatus) => void;
} | null>(null);

function useAvatarContext(component: string) {
  const context = React.useContext(AvatarContext);
  if (!context) throw new Error(`<${component}> must be rendered inside <Avatar>`);
  return context;
}

const avatarVariants = cva(
  'relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted',
  {
    variants: {
      size: {
        sm: 'size-8 text-xs',
        md: 'size-10 text-sm',
        lg: 'size-12 text-base',
      },
    },
    defaultVariants: { size: 'md' },
  },
);

export interface AvatarProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof avatarVariants> {}

export function Avatar({ className, size, ...props }: AvatarProps) {
  const [status, setStatus] = React.useState<ImageStatus>('loading');
  return (
    <AvatarContext.Provider value={{ status, setStatus }}>
      <span className={cn(avatarVariants({ size }), className)} {...props} />
    </AvatarContext.Provider>
  );
}

export interface AvatarImageProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  /** Required, not merely accepted: a person's photo is content, not decoration. */
  alt: string;
}

export function AvatarImage({ className, alt, onLoad, onError, ...props }: AvatarImageProps) {
  const { status, setStatus } = useAvatarContext('AvatarImage');

  return (
    // `next/image` needs a configured remote loader for arbitrary profile-photo
    // URLs, which is a deployment concern outside a UI primitive's reach; a
    // plain `<img>` is the right call for content this small either way.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt={alt}
      className={cn(
        'size-full object-cover',
        // Kept in the DOM (not unmounted) while loading or failed, so a
        // later `src` change can still fire `onLoad`/`onError` on the same
        // element — invisible rather than absent is what makes that work.
        status !== 'loaded' && 'hidden',
        className,
      )}
      onLoad={(event) => {
        setStatus('loaded');
        onLoad?.(event);
      }}
      onError={(event) => {
        setStatus('error');
        onError?.(event);
      }}
      {...props}
    />
  );
}

export function AvatarFallback({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  const { status } = useAvatarContext('AvatarFallback');
  if (status === 'loaded') return null;

  return (
    <span
      className={cn('font-medium uppercase text-muted-foreground', className)}
      {...props}
    />
  );
}
