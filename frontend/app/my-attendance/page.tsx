'use client';

import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
import {
  ATTENDANCE_STATUS_LABEL,
  ATTENDANCE_STATUS_VARIANT,
  formatTime,
} from '@/lib/academic-labels';
import { listMyAttendance } from '@/lib/academics';
import type { MyAttendance } from '@/types/api';

/**
 * A student's attendance, one card per enrolment.
 *
 * The requirement is shown next to the number, because "68%" on its own does
 * not tell a student whether they have a problem.
 */
function MyAttendancePage_() {
  const [rows, setRows] = useState<MyAttendance[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    listMyAttendance()
      .then((data) => {
        if (!cancelled) setRows(data);
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
  }, []);

  if (isLoading) return <LoadingState label="Loading your attendance…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your attendance"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My attendance</h1>
        <p className="text-sm text-muted-foreground">
          Every class you were on a register for, and how you stand against the requirement.
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing recorded yet"
          description="Attendance appears here once your trainer has taken a register."
        />
      ) : (
        rows.map((row) => {
          const { summary } = row;
          return (
            <Card key={row.enrollment_id} className="animate-rise-in">
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{row.batch_code}</span>
                  {summary.met === null ? null : (
                    <Badge variant={summary.met ? 'success' : 'error'}>
                      {summary.met ? 'Requirement met' : 'Below requirement'}
                    </Badge>
                  )}
                </div>
                <CardTitle>{row.course_title}</CardTitle>
                <CardDescription>
                  {summary.percentage === null
                    ? 'No classes counted yet.'
                    : `${summary.percentage}% attended`}
                  {summary.required
                    ? ` · ${summary.minimum_percent}% required`
                    : ' · attendance is not a completion requirement'}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
                  {(
                    [
                      ['Classes', summary.total_sessions],
                      ['Present', summary.present],
                      ['Late', summary.late],
                      ['Absent', summary.absent],
                      ['Excused', summary.excused],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-muted-foreground">{label}</dt>
                      <dd className="text-lg font-semibold">{value}</dd>
                    </div>
                  ))}
                </dl>

                {row.records.length > 0 ? (
                  <TableWrapper>
                    <Table>
                      <thead>
                        <tr>
                          <Th>Date</Th>
                          <Th>Class</Th>
                          <Th>Attendance</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {row.records.map((record) => (
                          <tr key={record.id}>
                            <Td>
                              {record.session_date} · {formatTime(record.start_time)}
                            </Td>
                            <Td>{record.topic || '—'}</Td>
                            <Td>
                              <Badge variant={ATTENDANCE_STATUS_VARIANT[record.status]}>
                                {ATTENDANCE_STATUS_LABEL[record.status]}
                              </Badge>
                              {record.note ? (
                                <span className="ml-2 text-xs text-muted-foreground">
                                  {record.note}
                                </span>
                              ) : null}
                            </Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </TableWrapper>
                ) : null}
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );
}

export default function MyAttendance() {
  return (
    <RequireAuth>
      <MyAttendancePage_ />
    </RequireAuth>
  );
}
