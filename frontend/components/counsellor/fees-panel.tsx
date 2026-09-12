/**
 * The counsellor's fees corner of the dashboard: what came in, what is
 * still out, and who is late — from `/api/v1/fees/overview/`, which the
 * server computes over live enrolments only.
 */
import { AlertTriangle, CalendarClock, IndianRupee, Wallet } from 'lucide-react';

import { money } from '@/components/fees/fee-ledger';
import { AlertList, type AlertItem } from '@/components/alert-list';
import { ErrorState, LoadingState } from '@/components/states';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BentoGrid, BentoTile, StatCard } from '@/components/ui/motion';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate } from '@/lib/format';
import type { FeePlanBrief, FeesOverview } from '@/types/api';

function planItem(plan: FeePlanBrief, severity: 'error' | 'warning'): AlertItem {
  return {
    id: plan.id,
    severity,
    title: plan.student_name || 'Unnamed student',
    description: `${plan.course_title || 'Course not available'} · ${money(plan.next_due_amount)} ${
      severity === 'error' ? 'was due' : 'expected'
    } ${formatDate(plan.next_due_on)} · ${money(plan.balance)} still owed`,
    href: plan.student_id ? `/admissions/${plan.student_id}` : undefined,
  };
}

function Tile({ isLoading, children }: { isLoading: boolean; children: React.ReactNode }) {
  if (!isLoading) return <>{children}</>;
  return (
    <Card className="h-full">
      <CardContent className="flex h-full flex-col justify-between gap-3 p-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-20" />
        <Skeleton className="h-3 w-32" />
      </CardContent>
    </Card>
  );
}

export function FeesPanel({
  overview,
  isLoading,
  error,
  onRetry,
}: {
  overview: FeesOverview | null;
  isLoading: boolean;
  error: { message: string; requestId?: string } | null;
  onRetry: () => void;
}) {
  const failed = Boolean(error);
  const value = (figure: string | undefined) =>
    failed || figure === undefined ? null : Number(figure);

  return (
    <div className="space-y-4">
      <BentoGrid>
        <BentoTile span={3} index={0}>
          <Tile isLoading={isLoading}>
            <StatCard
              label="Collected today"
              accent="green"
              prefix="₹"
              value={value(overview?.collected_today)}
              icon={IndianRupee}
              hint={overview ? `${money(overview.collected_this_week)} this week` : undefined}
            />
          </Tile>
        </BentoTile>
        <BentoTile span={3} index={1}>
          <Tile isLoading={isLoading}>
            <StatCard
              label="Collected this month"
              accent="blue"
              prefix="₹"
              value={value(overview?.collected_this_month)}
              icon={Wallet}
              hint="Voided payments excluded"
            />
          </Tile>
        </BentoTile>
        <BentoTile span={3} index={2}>
          <Tile isLoading={isLoading}>
            <StatCard
              label="Still owed"
              accent="amber"
              prefix="₹"
              value={value(overview?.outstanding_total)}
              icon={CalendarClock}
              hint={overview ? `${overview.unpaid_count} with nothing paid yet` : undefined}
            />
          </Tile>
        </BentoTile>
        <BentoTile span={3} index={3}>
          <Tile isLoading={isLoading}>
            <StatCard
              label="Overdue"
              accent="rose"
              value={failed ? null : overview?.overdue_count}
              icon={AlertTriangle}
              hint={
                overview && overview.enrollments_without_plan > 0
                  ? `${overview.enrollments_without_plan} enrolled with no fee set`
                  : 'Past their expected date'
              }
            />
          </Tile>
        </BentoTile>
      </BentoGrid>

      <div className="stagger grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Overdue</CardTitle>
            <CardDescription>An expected date has passed and the money has not.</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <LoadingState label="Loading overdue fees…" rows={3} />
            ) : error ? (
              <ErrorState
                title="Could not load fees"
                message={error.message}
                requestId={error.requestId}
                onRetry={onRetry}
              />
            ) : (
              <AlertList
                items={(overview?.overdue ?? []).map((plan) => planItem(plan, 'error'))}
                title="overdue fees"
                emptyTitle="Nobody is overdue"
                emptyDescription="Every expected payment is still ahead of its date."
              />
            )}
          </CardContent>
        </Card>
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Expected soon</CardTitle>
            <CardDescription>
              Payments students said they would bring, soonest first.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <LoadingState label="Loading expected payments…" rows={3} />
            ) : error ? (
              <ErrorState
                title="Could not load fees"
                message={error.message}
                requestId={error.requestId}
                onRetry={onRetry}
              />
            ) : (
              <AlertList
                items={(overview?.due_soon ?? []).map((plan) => planItem(plan, 'warning'))}
                title="expected payments"
                emptyTitle="Nothing scheduled"
                emptyDescription="Set an expected amount and date on a student's record to see it here."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
