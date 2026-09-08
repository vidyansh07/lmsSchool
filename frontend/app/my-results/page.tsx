'use client';

import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
import {
  ASSESSMENT_CATEGORY_LABEL,
  ASSESSMENT_DELIVERY_LABEL,
  formatDateTime,
} from '@/lib/academic-labels';
import { listMyAssessments, listMyResults } from '@/lib/assessments';
import type { AssessmentResult, StudentAssessment } from '@/types/api';

/** A student's tests: what is coming, and what they scored. */
function MyResults() {
  const [tests, setTests] = useState<StudentAssessment[]>([]);
  const [results, setResults] = useState<AssessmentResult[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listMyAssessments(), listMyResults()])
      .then(([assessments, marks]) => {
        if (cancelled) return;
        setTests(assessments.results);
        setResults(marks.results);
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

  if (isLoading) return <LoadingState label="Loading your tests…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your tests"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My tests and results</h1>
        <p className="text-sm text-muted-foreground">
          Weekly tests set on your batch, and the marks recorded for them.
        </p>
      </div>

      <Card className="animate-rise-in">
        <CardHeader>
          <CardTitle>Results</CardTitle>
          <CardDescription>Marks recorded against you.</CardDescription>
        </CardHeader>
        <CardContent>
          {results.length === 0 ? (
            <EmptyState
              title="No results yet"
              description="Marks appear here once your trainer records or imports them."
            />
          ) : (
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Test</Th>
                    <Th>Marks</Th>
                    <Th>Outcome</Th>
                    <Th>Recorded</Th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((result) => (
                    <tr key={result.id} data-testid="result-row">
                      <Td>
                        <div className="font-medium">{result.assessment_title}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {result.assessment_code}
                        </div>
                      </Td>
                      <Td>
                        {result.is_absent ? (
                          <Badge variant="warning">Absent</Badge>
                        ) : (
                          <>
                            <span className="font-semibold">{result.marks_obtained}</span>
                            <span className="text-muted-foreground"> / {result.max_marks}</span>
                            {result.percentage === null ? null : (
                              <span className="ml-2 text-xs text-muted-foreground">
                                {result.percentage}%
                              </span>
                            )}
                          </>
                        )}
                      </Td>
                      <Td>
                        {result.is_passing === null ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          <Badge variant={result.is_passing ? 'success' : 'error'}>
                            {result.is_passing ? 'Pass' : 'Below the pass mark'}
                          </Badge>
                        )}
                      </Td>
                      <Td>{formatDateTime(result.recorded_at)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
          )}
        </CardContent>
      </Card>

      <Card className="animate-rise-in">
        <CardHeader>
          <CardTitle>Scheduled tests</CardTitle>
        </CardHeader>
        <CardContent className="stagger space-y-3">
          {tests.length === 0 ? (
            <EmptyState title="Nothing scheduled" description="No tests are set on your batch." />
          ) : (
            tests.map((test) => (
              <div key={test.id} className="animate-rise-in rounded-md border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{test.code}</span>
                  <Badge variant={test.is_open ? 'success' : 'neutral'}>
                    {test.is_open ? 'Open' : 'Not open'}
                  </Badge>
                </div>
                <p className="mt-1 font-medium">{test.title}</p>
                <p className="text-sm text-muted-foreground">
                  {ASSESSMENT_CATEGORY_LABEL[test.category]} ·{' '}
                  {ASSESSMENT_DELIVERY_LABEL[test.delivery]} ·{' '}
                  {formatDateTime(test.scheduled_for)} · out of {test.max_marks}
                </p>
                {test.delivery === 'external_link' && test.external_url && test.is_open ? (
                  <Button asChild size="sm" className="mt-2">
                    <a href={test.external_url} target="_blank" rel="noreferrer noopener">
                      Take the test
                      {test.external_provider ? ` on ${test.external_provider}` : ''}
                    </a>
                  </Button>
                ) : null}
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function MyResultsPage() {
  return (
    <RequireAuth>
      <MyResults />
    </RequireAuth>
  );
}
