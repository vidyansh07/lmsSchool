'use client';

/**
 * Who is in class right now — online, in person, and together.
 *
 * Read from `GET /attendance/present-now/`, which counts today's saved
 * registers (present and late marks) by how each student joined, over the
 * classes the viewer may see. A class whose register is not taken yet adds
 * nothing, so the strip says how many of today's classes have been counted
 * rather than letting a half-marked day read as a quiet one.
 */
import { useEffect, useState } from 'react';

import { StatStrip } from '@/components/ui/stat-strip';
import { errorMessage } from '@/lib/api';
import { getPresentNow } from '@/lib/academics';
import type { PresentNow } from '@/types/api';

export function PresentNowStrip({ className }: { className?: string }) {
  const [state, setState] = useState<{ data: PresentNow | null; error: string }>({
    data: null,
    error: '',
  });

  useEffect(() => {
    let cancelled = false;
    getPresentNow()
      .then((data) => {
        if (!cancelled) setState({ data, error: '' });
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setState({ data: null, error: errorMessage(cause, 'Could not count who is present.') });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.error) {
    return (
      <p className="text-sm text-ink-muted" role="status" data-testid="present-now-error">
        Present today: {state.error}
      </p>
    );
  }
  const data = state.data;
  return (
    <section aria-label="Present today" className={className} data-testid="present-now">
      <StatStrip
        items={[
          { label: 'Present online', value: data?.online ?? null },
          { label: 'Present in person', value: data?.offline ?? null },
          { label: 'Present today', value: data?.total ?? null },
          {
            label: 'Registers taken',
            value: data?.registers_taken ?? null,
            suffix: data ? ` of ${data.sessions_today} classes` : undefined,
          },
        ]}
      />
    </section>
  );
}
