'use client';

/**
 * Two more parts of one student on Student 360, read where everything else
 * about them is read:
 *
 * - **Messages** — every email or SMS the platform sent them, with whether it
 *   arrived (`GET /deliveries/?recipient=<user>`, `communication.view_any`);
 * - **Certificates** — what they were awarded, live or revoked, with the
 *   public verification link (`GET /certificates/?student=<id>`, scoped to the
 *   caller's visible enrolments).
 *
 * Each loads when its tab is opened, and a failed load is an error with
 * Try again, never an empty list.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { CERTIFICATE_STATUS_LABEL, CERTIFICATE_STATUS_VARIANT } from '@/lib/academic-labels';
import { ApiError } from '@/lib/api';
import { listDeliveries } from '@/lib/communication';
import { formatDate, formatDateTime } from '@/lib/format';
import {
  COMMUNICATION_CHANNEL_LABEL,
  DELIVERY_STATE_LABEL,
  DELIVERY_STATE_VARIANT,
  labelFor,
} from '@/lib/labels';
import { listCertificates } from '@/lib/progress';
import type { Certificate, Delivery, Paginated } from '@/types/api';

function useLoad<T>(load: () => Promise<T>, key: string) {
  const [attempt, setAttempt] = useState(0);
  const requestKey = `${key}#${attempt}`;
  const [state, setState] = useState<{ key: string; data: T | null; error: ApiError | null }>({
    key: requestKey,
    data: null,
    error: null,
  });
  if (state.key !== requestKey) setState({ key: requestKey, data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    load()
      .then((data) => {
        if (!cancelled) setState({ key: requestKey, data, error: null });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            key: requestKey,
            data: null,
            error: cause instanceof ApiError ? cause : new ApiError(0, 'error', 'Could not load this.', ''),
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // `requestKey` carries every input the loader closes over.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  return { ...state, retry: () => setAttempt((value) => value + 1) };
}

export function StudentMessagesTab({ userId }: { userId: string }) {
  const { data, error, retry } = useLoad<Paginated<Delivery>>(
    () => listDeliveries({ recipient: userId }),
    userId,
  );
  if (error) {
    return (
      <ErrorState
        title="Could not load the messages"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={retry}
      />
    );
  }
  if (!data) return <LoadingState label="Loading messages…" rows={3} />;
  if (data.results.length === 0) {
    return <EmptyState title="No messages yet" description="Nothing has been sent to this student." />;
  }
  return (
    <TableWrapper>
      <Table>
        <thead>
          <tr>
            <Th>When</Th>
            <Th>How</Th>
            <Th>What</Th>
            <Th>Delivered</Th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((row) => (
            <tr key={row.id}>
              <Td className="whitespace-nowrap text-ink-muted">{formatDateTime(row.created_at)}</Td>
              <Td>{labelFor(COMMUNICATION_CHANNEL_LABEL, row.channel)}</Td>
              <Td>
                {row.template_key || 'Message'}
                {row.error ? <span className="block text-xs text-danger">{row.error}</span> : null}
              </Td>
              <Td>
                <Badge variant={DELIVERY_STATE_VARIANT[row.state]}>
                  {labelFor(DELIVERY_STATE_LABEL, row.state)}
                </Badge>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </TableWrapper>
  );
}

export function StudentCertificatesTab({ studentId }: { studentId: string }) {
  const { data, error, retry } = useLoad<Paginated<Certificate>>(
    () => listCertificates({ student: studentId }),
    studentId,
  );
  if (error) {
    return (
      <ErrorState
        title="Could not load the certificates"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={retry}
      />
    );
  }
  if (!data) return <LoadingState label="Loading certificates…" rows={3} />;
  if (data.results.length === 0) {
    return (
      <EmptyState
        title="No certificates yet"
        description="A certificate appears here once a completed course is approved and issued."
      />
    );
  }
  return (
    <TableWrapper>
      <Table>
        <thead>
          <tr>
            <Th>Number</Th>
            <Th>Course</Th>
            <Th>Completed</Th>
            <Th>Status</Th>
            <Th>Check</Th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((row) => (
            <tr key={row.id}>
              <Td className="font-mono text-xs">{row.number}</Td>
              <Td>
                {row.course_title}
                <span className="block font-mono text-xs text-ink-muted">{row.batch_code}</span>
              </Td>
              <Td className="whitespace-nowrap text-ink-muted">{formatDate(row.completion_date)}</Td>
              <Td>
                <Badge variant={CERTIFICATE_STATUS_VARIANT[row.status]}>
                  {CERTIFICATE_STATUS_LABEL[row.status]}
                </Badge>
              </Td>
              <Td>
                <Link
                  href={`/verify/${row.verification_code}`}
                  className="text-sm font-medium text-action hover:underline"
                >
                  Verify
                </Link>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </TableWrapper>
  );
}
