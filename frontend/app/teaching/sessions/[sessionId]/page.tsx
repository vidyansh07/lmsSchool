'use client';

import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, fieldErrors } from '@/lib/api';
import { ATTENDANCE_OPTIONS } from '@/lib/academic-labels';
import { getRegister, markAttendance } from '@/lib/academics';
import type { AttendanceStatus, Register } from '@/types/api';

/**
 * The class register.
 *
 * One screen, one save. The marks are held locally until the trainer presses
 * Save, and then sent as a single request — which is also how the backend
 * accepts them, so a dropped connection leaves the register untouched rather
 * than half-written.
 */
function RegisterScreen({ sessionId }: { sessionId: string }) {
  const [register, setRegister] = useState<Register | null>(null);
  const [marks, setMarks] = useState<Record<string, AttendanceStatus>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getRegister(sessionId)
      .then((data) => {
        if (cancelled) return;
        setRegister(data);
        setMarks(
          Object.fromEntries(
            data.entries
              .filter((entry) => entry.status !== null)
              .map((entry) => [entry.enrollment_id, entry.status as AttendanceStatus]),
          ),
        );
        setNotes(
          Object.fromEntries(data.entries.map((entry) => [entry.enrollment_id, entry.note])),
        );
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  async function save() {
    if (!register) return;
    setIsSaving(true);
    setFormError(null);
    setSaved(null);
    try {
      const result = await markAttendance(
        sessionId,
        register.entries.map((entry) => ({
          enrollment_id: entry.enrollment_id,
          // Nobody unmarked: a register with a gap in it is not a register.
          status: marks[entry.enrollment_id] ?? 'absent',
          note: notes[entry.enrollment_id] ?? '',
        })),
      );
      setSaved(
        `Saved. ${result.created} new, ${result.updated} updated` +
          (result.corrections ? `, ${result.corrections} corrected.` : '.'),
      );
      setRegister(await getRegister(sessionId));
    } catch (cause) {
      setFormError(fieldErrors(cause).__all__ ?? 'The register could not be saved.');
    } finally {
      setIsSaving(false);
    }
  }

  function markEveryone(status: AttendanceStatus) {
    if (!register) return;
    setMarks(Object.fromEntries(register.entries.map((entry) => [entry.enrollment_id, status])));
  }

  if (isLoading) return <LoadingState label="Loading the register…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the register"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!register) return null;

  return (
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Register</h1>
        <p className="text-sm text-muted-foreground">
          {register.batch_code} · {register.session_date}
        </p>
      </div>

      {!register.can_mark ? (
        <Alert variant="warning">
          This class cannot be marked. It may have been cancelled, or it may not have started
            yet.
        </Alert>
      ) : null}

      {formError ? (
        <Alert variant="error" role="alert">
          {formError}
        </Alert>
      ) : null}
      {saved ? (
        <Alert variant="success" role="status">
          {saved}
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{register.entries.length} students</CardTitle>
          <CardDescription>
            Mark the room, then save once. Re-saving records a correction rather than overwriting
            the history.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => markEveryone('present')}
              disabled={!register.can_mark}
            >
              Mark all present
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => markEveryone('absent')}
              disabled={!register.can_mark}
            >
              Mark all absent
            </Button>
          </div>

          <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
            <Table>
              <thead>
                <tr>
                  <Th className="sticky top-0 z-10 bg-muted">Student</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Attendance</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Note</Th>
                </tr>
              </thead>
              <tbody className="stagger">
                {register.entries.map((entry) => (
                  <tr key={entry.enrollment_id} className="animate-fade-in transition-colors hover:bg-muted/40">
                    <Td>
                      <div className="font-medium">{entry.full_name}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {entry.student_code}
                      </div>
                      {entry.was_corrected ? (
                        <Badge variant="warning" className="mt-1">
                          Corrected
                        </Badge>
                      ) : null}
                    </Td>
                    <Td>
                      <div
                        role="radiogroup"
                        aria-label={`Attendance for ${entry.full_name}`}
                        className="flex flex-wrap gap-1"
                      >
                        {ATTENDANCE_OPTIONS.map((option) => {
                          const active = marks[entry.enrollment_id] === option.value;
                          return (
                            <Button
                              key={option.value}
                              type="button"
                              role="radio"
                              aria-checked={active}
                              size="sm"
                              variant={active ? 'primary' : 'outline'}
                              disabled={!register.can_mark}
                              onClick={() =>
                                setMarks((current) => ({
                                  ...current,
                                  [entry.enrollment_id]: option.value,
                                }))
                              }
                            >
                              {option.label}
                            </Button>
                          );
                        })}
                      </div>
                    </Td>
                    <Td>
                      <Input
                        aria-label={`Note for ${entry.full_name}`}
                        value={notes[entry.enrollment_id] ?? ''}
                        disabled={!register.can_mark}
                        maxLength={255}
                        onChange={(event) =>
                          setNotes((current) => ({
                            ...current,
                            [entry.enrollment_id]: event.target.value,
                          }))
                        }
                      />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>

          <Button type="button" onClick={save} disabled={!register.can_mark || isSaving}>
            {isSaving ? 'Saving…' : 'Save register'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default function SessionRegisterPage() {
  const params = useParams<{ sessionId: string }>();
  return (
    <RequireAuth>
      <RegisterScreen sessionId={params.sessionId} />
    </RequireAuth>
  );
}
