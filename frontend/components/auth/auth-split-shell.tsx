import type { ReactNode } from 'react';
import { GraduationCap } from 'lucide-react';

/**
 * The frame every auth screen (`/login`, `/forgot-password`, `/reset-password`,
 * `/verify-email`) sits inside.
 *
 * These are the first screens anyone sees, and previously the plainest — a bare
 * card with no brand at all. `--color-brand`, the true Grras orange, belongs
 * here: it is decorative-only everywhere else in the product (never text, never
 * a button label — see `app/globals.css`), and a large panel of colour is
 * exactly the "decorative field" that colour exists for. The panel itself is
 * painted with `--color-primary`, not `--color-brand` — `primary` is the
 * darkened sibling `theme-contrast.test.ts` already guarantees clears 4.5:1
 * with `primary-foreground` text on it (a margin narrow enough, at 4.65:1,
 * that nothing in this file dims that text with an opacity modifier — that
 * would have been enough to fail AA). `--color-brand` supplies the texture on
 * top: two blurred, low-opacity fills, never sitting under the text itself.
 *
 * Mobile-first: below `lg` the panel collapses to a short band above the form
 * rather than a full-height side column, so the form — the actual task — is
 * one scroll away, not below a hero. Both halves are one card wherever
 * possible, since deep in a real product, the person reaching this
 * screen doesn't need a landing page — a real login screen once, fast.
 */
export function AuthSplitShell({
  heading,
  tagline,
  children,
}: {
  /** The panel's headline — what this screen is for, in a few words. */
  heading: string;
  /** One short supporting sentence under the headline. */
  tagline: string;
  /** The form pane's content: this page's own heading, copy and form. */
  children: ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-4xl animate-fade-in">
      <div className="overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface shadow-sm lg:grid lg:grid-cols-2">
        <div className="relative overflow-hidden bg-primary px-6 py-8 text-primary-foreground sm:px-10 sm:py-10 lg:flex lg:min-h-full lg:flex-col lg:justify-center lg:py-12">
          {/* Decorative only — the brand hue as a large fill, never carrying
              text. Blurred and kept away from the copy below so it can never
              become the background a reader has to see the words against. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-14 -top-16 size-56 rounded-full bg-brand/40 blur-3xl lg:size-72"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -bottom-20 -left-12 size-56 rounded-full bg-brand/25 blur-3xl lg:size-64"
          />
          <div className="relative space-y-3">
            <p className="flex items-center gap-2 text-sm font-semibold tracking-wide text-primary-foreground">
              <GraduationCap className="size-5" aria-hidden="true" />
              Grras LMS
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-primary-foreground sm:text-3xl">
              {heading}
            </h1>
            <p className="max-w-sm text-sm text-primary-foreground">{tagline}</p>
          </div>
        </div>

        <div className="animate-rise-in px-6 py-8 sm:px-10 sm:py-10 lg:flex lg:items-center lg:py-12">
          <div className="w-full">{children}</div>
        </div>
      </div>
    </div>
  );
}
