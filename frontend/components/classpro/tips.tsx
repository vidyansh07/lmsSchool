/**
 * The "Tips" column beside an admissions form.
 *
 * Kept as a real aside rather than a sidebar card: it is advice about the
 * form, so it belongs to the form, and a screen reader meets it after the
 * fields rather than before them. At phone width it moves below the form for
 * the same reason — nobody reads tips before they have seen what they are
 * tips about.
 */
import type { ReactNode } from 'react';

export function Tips({ children }: { children: ReactNode }) {
  return (
    <aside className="order-last space-y-3 text-sm text-ink-muted lg:order-none">
      <h2 className="text-xl font-normal text-ink">Tips</h2>
      {children}
    </aside>
  );
}
