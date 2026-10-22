'use client';

/**
 * The staff fee desk.
 *
 * Fee collection was already complete at record level, and the admissions
 * dashboard already carried the totals, but there was no destination called
 * "Fees". That made one of the institute's daily jobs discoverable only by
 * knowing which student to open first. This page turns the existing,
 * authorization-scoped fee APIs into a proper workspace: collections trend,
 * overdue and upcoming commitments, then direct paths to the payment ledger
 * and the student record where a payment is entered.
 */

import { Banknote, FileSpreadsheet, Search, UserPlus } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { FeesPanel } from '@/components/counsellor/fees-panel';
import { ReconciliationPanel } from '@/components/fees/reconciliation-panel';
import { RequireAuth } from '@/components/require-auth';
import { ErrorState } from '@/components/states';
import { Button } from '@/components/ui/button';
import { ChartCard, ComboChart } from '@/components/ui/charts';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/input';
import { Grid, GridItem, PageHeader, Section } from '@/components/ui/layout';
import { useSection } from '@/hooks/use-section';
import { formatWeekLabel } from '@/lib/analytics';
import { Capability } from '@/lib/capabilities';
import { feeCollectionsTrend, getFeesOverview, ledgerReconciliation } from '@/lib/fees';
import { formatCurrency, formatNumber } from '@/lib/format';
import type { FeeCollectionsTrendPoint, FeesOverview, LedgerReconciliation } from '@/types/api';

const PERIODS = [4, 12, 26, 52] as const;

export function FeesWorkspace() {
  const { can } = useAuth();
  const [weeks, setWeeks] = useState<number>(12);
  const overview = useSection<FeesOverview | null>(() => getFeesOverview(), null);
  const collections = useSection(
    () => feeCollectionsTrend({ weeks }),
    [] as FeeCollectionsTrendPoint[],
    [weeks],
  );
  // "Does it add up" is a separate question from "how are we doing", and a
  // separate fetch: a reconciliation that fails to load must not take the
  // collections figures down with it.
  const reconciliation = useSection<LedgerReconciliation | null>(() => ledgerReconciliation(), null);

  const trend = collections.data.map((point) => ({
    date: formatWeekLabel(point.week),
    amount: Number(point.amount),
    receipts: point.receipts,
  }));
  const mayViewReports = can(Capability.reportViewAny);
  const mayViewStudents = can(Capability.studentViewAny);
  const mayRegisterStudents = can(Capability.studentCreate);
  const mayViewAdmissions = can(Capability.enrolmentViewAny);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Fees & collections"
        meta="Collections, commitments and overdue balances across the students you are allowed to see."
      >
        {mayViewReports ? (
          <Button asChild variant="outline">
            <Link href="/admin/reports?report=fee_payments">
              <FileSpreadsheet className="size-4" aria-hidden="true" />
              Payment ledger
            </Link>
          </Button>
        ) : null}
        {mayViewStudents ? (
          <Button asChild>
            <Link href="/admin/students">
              <Search className="size-4" aria-hidden="true" />
              Find a student
            </Link>
          </Button>
        ) : null}
      </PageHeader>

      {mayRegisterStudents || mayViewAdmissions ? (
        <div className="flex flex-wrap gap-2">
          {mayRegisterStudents ? (
            <Button asChild variant="ghost" size="sm">
              <Link href="/admissions/new">
                <UserPlus className="size-4" aria-hidden="true" />
                Register a student
              </Link>
            </Button>
          ) : null}
          {mayViewAdmissions ? (
            <Button asChild variant="ghost" size="sm">
              <Link href="/admissions">
                <Banknote className="size-4" aria-hidden="true" />
                Open registrations
              </Link>
            </Button>
          ) : null}
        </div>
      ) : null}

      <Section title="Current position" meta="Live fee plans; voided receipts are excluded">
        <FeesPanel
          overview={overview.data}
          isLoading={overview.isLoading}
          error={
            overview.error
              ? {
                  message: overview.error.message,
                  requestId: overview.error.requestId || undefined,
                }
              : null
          }
          onRetry={overview.reload}
        />
      </Section>

      <Section
        title="Does it add up?"
        meta="Every rupee charged — cancellations included — placed in exactly one bucket"
      >
        <ReconciliationPanel
          data={reconciliation.data}
          isLoading={reconciliation.isLoading}
          error={
            reconciliation.error
              ? {
                  message: reconciliation.error.message,
                  requestId: reconciliation.error.requestId || undefined,
                }
              : null
          }
          onRetry={reconciliation.reload}
        />
      </Section>

      <Grid>
        <GridItem span={12}>
          <ChartCard
            title="Collections over time"
            subtitle={`Money received and receipts issued in each of the last ${weeks} weeks — voided receipts excluded`}
            icon={Banknote}
            iconTone="success"
            testId="fee-collections-workspace-card"
            actions={
              <Field label="Period" htmlFor="fee-period" className="min-w-36">
                <Select
                  id="fee-period"
                  value={String(weeks)}
                  onChange={(event) => setWeeks(Number(event.target.value))}
                >
                  {PERIODS.map((period) => (
                    <option key={period} value={period}>
                      Last {period} weeks
                    </option>
                  ))}
                </Select>
              </Field>
            }
            footer={
              mayViewReports ? (
                <Link
                  href="/admin/reports?report=fee_payments"
                  className="font-medium text-action hover:underline"
                >
                  Open every payment →
                </Link>
              ) : undefined
            }
          >
            {collections.error ? (
              <ErrorState
                title="The collections trend did not load"
                message={collections.error.message}
                requestId={collections.error.requestId || undefined}
                onRetry={collections.reload}
              />
            ) : (
              <ComboChart
                data={trend}
                bars={[{ key: 'amount', label: 'Collected' }]}
                lines={[{ key: 'receipts', label: 'Receipts' }]}
                rightAxisKeys={['receipts']}
                leftLabel="Rupees"
                rightLabel="Receipts"
                xLabel="Week"
                height={280}
                loading={collections.isLoading}
                emptyMessage="No payments were recorded in this period"
                valueFormatter={(value) => formatCurrency(value)}
                rightValueFormatter={(value) => formatNumber(value)}
              />
            )}
          </ChartCard>
        </GridItem>
      </Grid>
    </div>
  );
}

export default function FeesPage() {
  return (
    <RequireAuth capability={Capability.feeViewAny}>
      <FeesWorkspace />
    </RequireAuth>
  );
}
