/**
 * The counsellor dashboard's fees corner: figures from the overview, and the
 * overdue list pointing at the student's record.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FeesPanel } from '@/components/counsellor/fees-panel';
import type { FeesOverview } from '@/types/api';

const overview: FeesOverview = {
  collected_today: '3000.00',
  collected_this_week: '12000.00',
  collected_this_month: '40000.00',
  outstanding_total: '95000.00',
  overdue_count: 1,
  unpaid_count: 2,
  enrollments_without_plan: 3,
  overdue: [
    {
      id: 'plan-1',
      enrollment_id: 'enrol-1',
      enrollment_code: 'GRS-E-00001',
      enrollment_status: 'active',
      course_title: 'Linux Essentials',
      batch_code: 'GRS-B-00001',
      batch_name: 'Morning',
      agreed_amount: '10000.00',
      discount_amount: '0.00',
      discount_reason: '',
      payable: '10000.00',
      paid: '1000.00',
      balance: '9000.00',
      status: 'partial',
      next_due_amount: '4000.00',
      next_due_on: '2026-08-30',
      is_overdue: true,
      notes: '',
      created_by: null,
      updated_by: null,
      created_at: '2026-09-01T10:00:00Z',
      updated_at: '2026-09-01T10:00:00Z',
      student_id: 'student-1',
      student_name: 'Asha Verma',
    },
  ],
  due_soon: [],
};

describe('FeesPanel', () => {
  it('shows collections, what is owed, and who is late', async () => {
    render(<FeesPanel overview={overview} isLoading={false} error={null} onRetry={vi.fn()} />);
    expect(screen.getByText('Collected today')).toBeInTheDocument();
    expect(screen.getByText('₹12,000 this week')).toBeInTheDocument();
    expect(screen.getByText('3 enrolled with no fee set')).toBeInTheDocument();
    const late = await screen.findByText('Asha Verma');
    expect(late.closest('a')).toHaveAttribute('href', '/admissions/student-1');
    expect(screen.getByText(/₹4,000 was due/)).toBeInTheDocument();
    expect(screen.getByText('Nothing scheduled')).toBeInTheDocument();
  });

  it('says so when the numbers could not be loaded', () => {
    render(
      <FeesPanel overview={null} isLoading={false} error={{ message: 'Boom' }} onRetry={vi.fn()} />,
    );
    expect(screen.getAllByText('Boom').length).toBeGreaterThan(0);
  });
});
