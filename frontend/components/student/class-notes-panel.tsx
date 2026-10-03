'use client';

/**
 * "What we covered" — a student's view of their recent classes, from the
 * trainer's submitted class reports (`GET /dsr/mine/`): the topic, the
 * lessons, and the homework. Never the trainer's own notes; the endpoint
 * does not send them. Renders nothing until there is something to show.
 */
import { BookOpenCheck } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useApi } from '@/hooks/use-api';
import type { StudentClassNote } from '@/lib/dsr';
import { formatDate } from '@/lib/format';
import type { Paginated } from '@/types/api';

const SHOWN = 8;

export function ClassNotesPanel() {
  const notes = useApi<Paginated<StudentClassNote>>('/api/v1/dsr/mine/');
  const rows = notes.data?.results.slice(0, SHOWN) ?? [];
  // A failed or empty load is quiet: this panel is a convenience next to the
  // batch list, not the page's subject.
  if (rows.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle as="h2" className="flex items-center gap-2">
          <BookOpenCheck className="size-4 text-action" aria-hidden="true" />
          What we covered
        </CardTitle>
        <CardDescription>Your recent classes, as your trainer reported them.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-line">
          {rows.map((row) => {
            const lessons = row.lessons_covered.map((lesson) => lesson.title).join(', ');
            return (
              <li key={row.id} className="space-y-0.5 py-2.5 text-sm">
                <p className="text-xs text-ink-muted">
                  {formatDate(row.report_date)} · <span className="font-mono">{row.batch_code}</span>
                  {row.trainer_name ? ` · ${row.trainer_name}` : ''}
                </p>
                <p className="font-medium text-ink">{row.topic || lessons || 'Class held'}</p>
                {row.topic && lessons ? <p className="text-ink-muted">{lessons}</p> : null}
                {row.homework ? (
                  <p>
                    <span className="font-medium">Homework:</span> {row.homework}
                    {row.homework_due_on ? (
                      <span className="text-ink-muted"> (due {formatDate(row.homework_due_on)})</span>
                    ) : null}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
