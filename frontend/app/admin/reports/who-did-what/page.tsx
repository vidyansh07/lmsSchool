'use client';

/**
 * Who did what, between two dates.
 *
 * The first of the two report modes: pick a person, pick a span, read what
 * they did. "For a counsellor from April to June, what did he do" was the
 * question asked, and the answer is one screen rather than nine reports read
 * in sequence and added up by hand.
 *
 * It is deliberately thin. Everything it shows comes from the staff record
 * engine (`GET /users/<id>/record/`), which counts from each table's own
 * record of who did the work and carries the audit trail as the detail
 * underneath. So this page owns the *choosing* — which person, which dates —
 * and nothing else, and anything added to that engine appears here with no
 * change at all.
 *
 * Who can open it: `staff.view_record`, which is administrators and
 * superadmins. A person's own record is on their own account page, where
 * they will look for it; sending somebody to a reports screen to read about
 * themselves is the wrong shape.
 *
 * The person list is the caller's own visible accounts, so a composed
 * administrator role bounded to one centre picks from that centre.
 */

import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { StaffRecordCard } from '@/components/people/staff-record-card';
import { ErrorState } from '@/components/states';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/layout';
import { errorMessage } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { listUsers } from '@/lib/people';
import type { AdminUser } from '@/types/api';

/** Students are not staff, and a record of "what this student did" is a
 *  different question answered by their own timeline. */
const STAFF_ROLES = ['superadmin', 'admin', 'manager', 'counsellor', 'trainer'];

export function WhoDidWhat() {
  const [people, setPeople] = useState<AdminUser[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [chosen, setChosen] = useState('');

  useEffect(() => {
    let cancelled = false;
    listUsers({ page_size: 200, ordering: 'full_name' })
      .then((page) => {
        if (!cancelled) {
          setPeople(page.results.filter((person) => STAFF_ROLES.includes(person.role)));
          setFailure(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setFailure(errorMessage(cause, 'Could not read the staff list.'));
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Who did what"
        meta="Pick a person and a span of dates. Everything is counted from the record of who did the work."
      />

      {failure ? (
        <ErrorState message={failure} onRetry={() => setAttempt((value) => value + 1)} />
      ) : (
        <div className="max-w-sm">
          <Field
            label="Person"
            htmlFor="who-person"
            hint="Staff at the centres you can see."
          >
            <Select
              id="who-person"
              value={chosen}
              onChange={(event) => setChosen(event.target.value)}
            >
              <option value="">Choose somebody</option>
              {(people ?? []).map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name || person.email} · {person.role}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      )}

      {chosen ? (
        // Keyed by the person, so choosing a second one starts their record
        // afresh rather than showing the first one's figures under a new name
        // while the next request is in flight.
        <StaffRecordCard key={chosen} userId={chosen} />
      ) : (
        <p className="text-sm text-ink-muted">
          Nobody chosen yet. A person&rsquo;s own record is also on their account page.
        </p>
      )}
    </div>
  );
}

export default function WhoDidWhatPage() {
  return (
    <RequireAuth capability={Capability.staffViewRecord}>
      <WhoDidWhat />
    </RequireAuth>
  );
}
