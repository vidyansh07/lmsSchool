import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FeesWorkspace } from '@/app/fees/page';
import { Capability } from '@/lib/capabilities';
import type { FeesOverview, LedgerReconciliation } from '@/types/api';

const getFeesOverview = vi.hoisted(() => vi.fn());
const feeCollectionsTrend = vi.hoisted(() => vi.fn());
const ledgerReconciliation = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fees', () => ({ getFeesOverview, feeCollectionsTrend, ledgerReconciliation }));

const allowedCapabilities = vi.hoisted(() => ({
  value: new Set<string>(),
}));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ can: (capability: string) => allowedCapabilities.value.has(capability) }),
}));

const OVERVIEW: FeesOverview = {
  collected_today: '3000.00',
  collected_this_week: '12000.00',
  collected_this_month: '40000.00',
  outstanding_total: '95000.00',
  overdue_count: 0,
  unpaid_count: 2,
  enrollments_without_plan: 1,
  overdue: [],
  due_soon: [],
};

/** A ledger that balances: what was charged is exactly held − owed back +
 *  written off + still owed, so `unreconciled` is zero. */
const BALANCED: LedgerReconciliation = {
  charged: '500000.00',
  received: '300000.00',
  refunded: '5000.00',
  refund_due: '10000.00',
  written_off: '40000.00',
  outstanding: '170000.00',
  unreconciled: '0.00',
  cancelled_enrolments: 3,
};

describe('FeesWorkspace', () => {
  beforeEach(() => {
    allowedCapabilities.value = new Set<string>(Object.values(Capability));
    getFeesOverview.mockReset();
    feeCollectionsTrend.mockReset();
    getFeesOverview.mockResolvedValue(OVERVIEW);
    feeCollectionsTrend.mockResolvedValue([
      { week: '2026-10-12', amount: '12000.00', receipts: 3 },
    ]);
    ledgerReconciliation.mockReset();
    ledgerReconciliation.mockResolvedValue(BALANCED);
  });

  it('makes the existing fee overview, ledger and student lookup one discoverable workspace', async () => {
    render(<FeesWorkspace />);

    expect(await screen.findByText('Collected today')).toBeInTheDocument();
    expect(screen.getByText('₹12,000 this week')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Payment ledger/i })).toHaveAttribute(
      'href',
      '/admin/reports?report=fee_payments',
    );
    expect(screen.getByRole('link', { name: /Find a student/i })).toHaveAttribute(
      'href',
      '/admin/students',
    );
    expect(await screen.findByTestId('fee-collections-workspace-card')).toBeInTheDocument();
    expect(feeCollectionsTrend).toHaveBeenCalledWith({ weeks: 12 });
  });

  it('refetches the collections chart when the period changes', async () => {
    render(<FeesWorkspace />);
    await screen.findByText('Collected today');

    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '26' } });

    await waitFor(() => expect(feeCollectionsTrend).toHaveBeenCalledWith({ weeks: 26 }));
  });

  it('states what was charged and where every rupee of it went', async () => {
    render(<FeesWorkspace />);

    expect(await screen.findByText('Every rupee charged is accounted for.')).toBeInTheDocument();
    // Scoped to this card: ₹40,000 is also the month's collections in the
    // panel above, and an unscoped query cannot tell which figure it found.
    const card = within(screen.getByTestId('fee-reconciliation'));
    expect(card.getByText('₹5,00,000')).toBeInTheDocument();
    expect(card.getByText('₹3,00,000')).toBeInTheDocument();
    // Money held that is owed back comes off the total, and says so.
    expect(card.getByText('− ₹10,000')).toBeInTheDocument();
    expect(card.getByText('₹40,000')).toBeInTheDocument();
    expect(card.getByText('₹1,70,000')).toBeInTheDocument();
    // A cancelled admission is still counted, which is the whole point.
    expect(card.getByText('3 admissions')).toBeInTheDocument();
    expect(card.queryByText('Not accounted for')).not.toBeInTheDocument();
  });

  it('says plainly when the ledger does not add up, rather than hiding the remainder', async () => {
    ledgerReconciliation.mockResolvedValue({ ...BALANCED, unreconciled: '2500.00' });
    render(<FeesWorkspace />);

    expect(await screen.findByText(/₹2,500 is not accounted for/)).toBeInTheDocument();
    expect(screen.getByText('Not accounted for')).toBeInTheDocument();
  });

  it('keeps the collections figures when the reconciliation fails to load', async () => {
    ledgerReconciliation.mockRejectedValue(new Error('Reconciliation is down.'));
    render(<FeesWorkspace />);

    expect(await screen.findByText('Collected today')).toBeInTheDocument();
    expect(await screen.findByText('The reconciliation did not load')).toBeInTheDocument();
  });

  it('hides shortcuts that a fee-only custom role cannot open', async () => {
    allowedCapabilities.value = new Set([Capability.feeViewAny]);
    render(<FeesWorkspace />);

    expect(await screen.findByText('Collected today')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Payment ledger/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Find a student/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Register a student/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open registrations/i })).not.toBeInTheDocument();
  });
});
