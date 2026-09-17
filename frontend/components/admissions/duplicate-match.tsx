import Link from 'next/link';
import { useState } from 'react';

import { Alert, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/input';
import { formatDate } from '@/lib/batch-labels';
import type { StudentDuplicateMatch } from '@/types/api';

/**
 * The warning that stands between a counsellor and a second record for the
 * same person — `USER_JOURNEYS.md` §4.2's "Possible existing student found".
 *
 * Shown while the registration form is still being filled in — before there
 * is anything to submit — because a duplicate created is expensive to unpick
 * (two fee histories, two enrolment trails) and a duplicate merely warned
 * about costs nothing. It never blocks outright: sometimes the match is a
 * coincidence, so the counsellor can continue, but only after typing why —
 * same shape as `PurgeControl`'s reason field (`components/recovery/
 * purge-control.tsx`): the confirming action stays disabled until the
 * reason is non-blank, so a blank override can never reach the server.
 *
 * `matches` comes from the disclosure-safe `checkDuplicates` (`lib/people
 * .ts`), never a plain student search — an empty list here may mean either
 * "nobody matches" or "somebody matches outside your reach", and this
 * component has no way to tell the difference, by design.
 */
export function DuplicateMatch({
  matches,
  onConfirmDifferentPerson,
}: {
  matches: StudentDuplicateMatch[];
  onConfirmDifferentPerson: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');

  if (matches.length === 0) return null;

  return (
    <Alert variant="warning" className="space-y-3" data-testid="duplicate-warning">
      <AlertTitle>
        {matches.length === 1
          ? 'Possible existing student found'
          : `${matches.length} possible existing students found`}
      </AlertTitle>
      <ul className="space-y-2">
        {matches.map((match) => (
          <li key={match.id} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              <span className="font-medium">{match.name}</span>{' '}
              <span className="text-muted-foreground">
                · {match.student_id}
                {match.batch_code ? ` · ${match.batch_code}` : ''} · registered{' '}
                {formatDate(match.created_at)}
              </span>
            </span>
            <Button asChild size="sm" variant="outline">
              <Link href={`/admissions/${match.id}`}>Open that record</Link>
            </Button>
          </li>
        ))}
      </ul>
      <div className="space-y-2">
        <label htmlFor="duplicate-override-reason" className="block text-xs font-medium">
          This is a different person — why?
        </label>
        <Textarea
          id="duplicate-override-reason"
          rows={2}
          className="text-xs"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Required to continue registering."
        />
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={!reason.trim()}
          onClick={() => onConfirmDifferentPerson(reason.trim())}
        >
          Continue registering — different person
        </Button>
      </div>
    </Alert>
  );
}
