'use client';

/**
 * Ready to admit: the leads Meritto sent because they reached its admission
 * stage, not yet registered here. Meritto runs their pipeline (owner's
 * decision, 17 October 2026); the counsellor's one job on each is to register
 * it — the wizard, filled in from the lead, which marks it registered.
 */

import Link from 'next/link';
import { useState } from 'react';
import { UserPlus } from 'lucide-react';

import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/layout';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useApi } from '@/hooks/use-api';
import { errorMessage } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { enquiryListPath, registerLeadHref } from '@/lib/enquiries';
import { formatDateTime } from '@/lib/format';
import type { Enquiry, Paginated } from '@/types/api';

const PAGE_SIZE = 25;

function ReadyToAdmit() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const list = useApi<Paginated<Enquiry>>(
    enquiryListPath({ ready_to_admit: true, q: search.trim(), page }),
  );
  const rows = list.data?.results ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ready to admit"
        meta="Leads Meritto sent when they reached its admission stage. Register each one here."
      >
        <Button asChild variant="outline">
          <Link href="/students/new">
            <UserPlus className="size-4" aria-hidden="true" />
            Register a walk-in
          </Link>
        </Button>
      </PageHeader>

      <Input
        aria-label="Search leads"
        placeholder="Search name, mobile or email"
        value={search}
        onChange={(event) => {
          setSearch(event.target.value);
          setPage(1);
        }}
        className="max-w-sm"
      />

      {list.error ? (
        <ErrorState
          title="Could not load the leads"
          message={errorMessage(list.error)}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.isLoading && !list.data ? (
        <LoadingState label="Loading leads…" rows={4} />
      ) : rows.length === 0 ? (
        <EmptyState
          title={search.trim() ? 'No lead matches that search' : 'Nothing waiting'}
          description={
            search.trim()
              ? 'Try another name or number.'
              : 'When Meritto sends a lead that is ready to admit, it appears here.'
          }
        />
      ) : (
        <div className="space-y-3">
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Lead</Th>
                  <Th>Course</Th>
                  <Th>Stage in Meritto</Th>
                  <Th>Owner in Meritto</Th>
                  <Th>Received</Th>
                  <Th className="text-right">Action</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-line last:border-0">
                    <Td>
                      <Link
                        href={`/enquiries/${row.id}`}
                        className="font-medium text-ink underline-offset-2 hover:underline"
                      >
                        {row.full_name}
                      </Link>
                      <span className="block text-2xs tabular-nums text-ink-faint">
                        {row.mobile}
                        {row.email ? ` · ${row.email}` : ''}
                      </span>
                    </Td>
                    <Td>{row.course || '—'}</Td>
                    <Td>
                      {row.external_stage ? (
                        <Badge variant="info">{row.external_stage}</Badge>
                      ) : (
                        '—'
                      )}
                    </Td>
                    <Td>{row.external_owner || '—'}</Td>
                    <Td className="whitespace-nowrap tabular-nums">
                      {formatDateTime(row.created_at)}
                    </Td>
                    <Td className="text-right">
                      {row.can_register ? (
                        <Button asChild size="sm">
                          <Link href={registerLeadHref(row.id)}>Register</Link>
                        </Button>
                      ) : (
                        <span className="text-xs text-ink-faint">Not yours to register</span>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
          {list.data && (list.data.next || list.data.previous) ? (
            <Pagination
              page={page}
              totalPages={Math.max(1, Math.ceil(list.data.count / PAGE_SIZE))}
              count={list.data.count}
              pageSize={PAGE_SIZE}
              onPageChange={setPage}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function ReadyToAdmitPage() {
  return (
    <RequireAuth capability={Capability.studentCreate}>
      <ReadyToAdmit />
    </RequireAuth>
  );
}
