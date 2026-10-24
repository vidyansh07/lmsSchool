'use client';

/**
 * Academic years: the record an admission is filed under.
 *
 * A year is not a number read off a date. An institute admits for next year
 * in December, and the counsellor doing that has to be able to say so — which
 * is why this is a list with dates and a "current" switch rather than
 * `date.today().year`.
 *
 * Two rules the screen makes visible:
 *
 * * **Exactly one year is current.** Pressing the switch on another year
 *   moves it; there is no way to switch it off, because the institute always
 *   has one. The server enforces the same thing in one transaction.
 * * **A closed year takes no new admissions**, and its records are untouched
 *   — closing is not deleting, and nothing here deletes.
 */

import { useState } from 'react';
import { Plus } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { errorMessage } from '@/lib/api';
import {
  createAcademicYear,
  updateAcademicYear,
  type AcademicYear,
} from '@/lib/academic-years';
import { formatDate } from '@/lib/format';

export function AcademicYearsCard({
  years,
  canManage,
  onChanged,
}: {
  years: AcademicYear[];
  canManage: boolean;
  onChanged: () => void;
}) {
  const [name, setName] = useState('');
  const [startsOn, setStartsOn] = useState('');
  const [endsOn, setEndsOn] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function run(work: () => Promise<unknown>) {
    setBusy(true);
    setFailure(null);
    try {
      await work();
      onChanged();
    } catch (cause) {
      setFailure(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Academic Year</CardTitle>
        <CardDescription>
          What an admission is filed under. One year is current — the one a new admission starts
          with — and a closed year takes no new admissions while keeping everything already filed
          under it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {failure ? <Alert variant="error">{failure}</Alert> : null}

        {years.length === 0 ? (
          <p className="text-sm text-ink-muted">No academic year yet.</p>
        ) : (
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Year</Th>
                  <Th>Runs</Th>
                  <Th>Current</Th>
                  <Th>Open</Th>
                </tr>
              </thead>
              <tbody>
                {years.map((year) => (
                  <tr key={year.id} className="hover:bg-sunken/40">
                    <Td>
                      {year.name}
                      {year.is_current ? (
                        <Badge variant="success" className="ml-2">
                          Current
                        </Badge>
                      ) : null}
                    </Td>
                    <Td className="whitespace-nowrap tabular-nums">
                      {year.starts_on ? formatDate(year.starts_on) : '—'} to{' '}
                      {year.ends_on ? formatDate(year.ends_on) : '—'}
                    </Td>
                    <Td>
                      <Switch
                        aria-label={`${year.name} is the current year`}
                        checked={year.is_current}
                        // Off is not an option: the way to move it is to
                        // switch it on somewhere else.
                        disabled={!canManage || busy || year.is_current}
                        onCheckedChange={() =>
                          void run(() => updateAcademicYear(year.id, { is_current: true }))
                        }
                      />
                    </Td>
                    <Td>
                      <Switch
                        aria-label={`${year.name} takes new admissions`}
                        checked={!year.is_closed}
                        disabled={!canManage || busy}
                        onCheckedChange={(checked) =>
                          void run(() => updateAcademicYear(year.id, { is_closed: !checked }))
                        }
                      />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
        )}

        {canManage ? (
          <form
            className="grid gap-3 border-t border-line pt-4 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              const typed = name.trim();
              if (!typed) {
                setFailure('Give the year a name — "2026-27" is how people say it.');
                return;
              }
              void run(async () => {
                await createAcademicYear({
                  name: typed,
                  starts_on: startsOn || null,
                  ends_on: endsOn || null,
                });
                setName('');
                setStartsOn('');
                setEndsOn('');
              });
            }}
            noValidate
          >
            <Field label="Year" htmlFor="year-name">
              <Input
                id="year-name"
                value={name}
                placeholder="2026-27"
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
            <Field label="Starts on" htmlFor="year-starts">
              <Input
                id="year-starts"
                type="date"
                value={startsOn}
                onChange={(event) => setStartsOn(event.target.value)}
              />
            </Field>
            <Field label="Ends on" htmlFor="year-ends">
              <Input
                id="year-ends"
                type="date"
                value={endsOn}
                onChange={(event) => setEndsOn(event.target.value)}
              />
            </Field>
            <Button type="submit" variant="outline" className="mb-0.5" disabled={busy}>
              <Plus className="size-4" aria-hidden="true" />
              Add
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
