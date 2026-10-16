import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FeesWorkspace } from '@/app/fees/page';
import { Capability } from '@/lib/capabilities';
import type { FeesOverview } from '@/types/api';

const getFeesOverview = vi.hoisted(() => vi.fn());
const feeCollectionsTrend = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fees', () => ({ getFeesOverview, feeCollectionsTrend }));

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

describe('FeesWorkspace', () => {
  beforeEach(() => {
    allowedCapabilities.value = new Set<string>(Object.values(Capability));
    getFeesOverview.mockReset();
    feeCollectionsTrend.mockReset();
    getFeesOverview.mockResolvedValue(OVERVIEW);
    feeCollectionsTrend.mockResolvedValue([
      { week: '2026-10-12', amount: '12000.00', receipts: 3 },
    ]);
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
