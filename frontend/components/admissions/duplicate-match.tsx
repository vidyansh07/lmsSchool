import Link from 'next/link';

import { Alert, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import type { StudentListRow } from '@/types/api';

/**
 * The warning that stands between a counsellor and a second record for the
 * same person.
 *
 * Shown while the registration form is still being filled in — before there
 * is anything to submit — because a duplicate created is expensive to unpick
 * (two fee histories, two enrolment trails) and a duplicate merely warned
 * about costs nothing. It never blocks outright: sometimes the match is a
 * coincidence, so the counsellor can see it and still choose to continue.
 */
export function DuplicateMatch({
  matches,
  onContinueAnyway,
}: {
  matches: StudentListRow[];
  onContinueAnyway: () => void;
}) {
  if (matches.length === 0) return null;

  return (
    <Alert variant="warning" className="space-y-3" data-testid="duplicate-warning">
      <AlertTitle>
        {matches.length === 1
          ? 'This looks like an existing student'
          : `${matches.length} existing students look like a match`}
      </AlertTitle>
      <ul className="space-y-1">
        {matches.map((match) => (
          <li key={match.id} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              <span className="font-medium">{match.full_name || match.email}</span>{' '}
              <span className="text-muted-foreground">
                · {match.email} · {match.student_id}
              </span>
            </span>
            <Button asChild size="sm" variant="outline">
              <Link href={`/admissions/${match.id}`}>Open this record</Link>
            </Button>
          </li>
        ))}
      </ul>
      <Button type="button" size="sm" variant="ghost" onClick={onContinueAnyway}>
        This is a different person — continue registering
      </Button>
    </Alert>
  );
}
