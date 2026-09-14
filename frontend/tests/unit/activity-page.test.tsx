/**
 * The activity review: scorecards from the server, the feed as sentences,
 * and clicking a person narrows the feed to them.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ActivityReview } from '@/app/admin/activity/page';
import type { ActivityFeedEntry, ActivityScorecards, Paginated } from '@/types/api';

const getActivityFeed = vi.hoisted(() => vi.fn());
const getActivityScorecards = vi.hoisted(() => vi.fn());

vi.mock('@/lib/activity', () => ({ getActivityFeed, getActivityScorecards }));
// The export menu has its own test; here it needs a toast provider the page does not.
vi.mock('@/components/export-menu', () => ({ ExportMenu: () => null }));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ user: { role: 'admin', capabilities: ['audit.view'] }, can: () => true }),
}));

const cards: ActivityScorecards = {
  since: '2026-09-14',
  until: '2026-09-14',
  cards: [
    {
      user_id: 'u-kiran',
      name: 'Kiran Counsellor',
      email: 'kiran@example.test',
      role: 'counsellor',
      branch_name: 'Main centre',
      total_actions: 7,
      fees_collected: '5000.00',
      last_active_at: new Date().toISOString(),
      figures: [
        { key: 'students_registered', label: 'Students registered', value: 3 },
        { key: 'enrolments', label: 'Enrolments', value: 2 },
        { key: 'payments_recorded', label: 'Payments recorded', value: 1 },
        { key: 'batches_opened', label: 'Batches opened', value: 0 },
      ],
    },
  ],
};

function feed(results: ActivityFeedEntry[]): Paginated<ActivityFeedEntry> {
  return {
    count: results.length,
    page: 1,
    page_size: 25,
    total_pages: 1,
    next: null,
    previous: null,
    results,
  };
}

const entry: ActivityFeedEntry = {
  id: 'e1',
  created_at: new Date().toISOString(),
  action: 'fee.payment.recorded',
  action_label: 'Payment recorded',
  kind: 'fees',
  actor_id: 'u-kiran',
  actor_label: 'kiran@example.test',
  actor_role: 'counsellor',
  actor_branch: 'Main centre',
  resource_type: 'fee_payment',
  resource_id: 'p1',
  summary: 'Received ₹5,000 by upi (receipt GRS-R-00001); balance ₹7,000',
  href: '/admissions/s1',
  context: {},
};

describe('ActivityReview', () => {
  it('shows the scorecards and the record, and narrows to a person on click', async () => {
    getActivityScorecards.mockResolvedValue(cards);
    getActivityFeed.mockResolvedValue(feed([entry]));
    render(<ActivityReview />);

    expect(await screen.findByText('Kiran Counsellor')).toBeInTheDocument();
    expect(screen.getByText('₹5,000 collected')).toBeInTheDocument();
    expect(screen.getByText('Students registered')).toBeInTheDocument();
    expect(await screen.findByText(/Received ₹5,000 by upi/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open fee_payment/i })).toHaveAttribute(
      'href',
      '/admissions/s1',
    );

    fireEvent.click(screen.getByRole('button', { name: /Kiran Counsellor/ }));
    await waitFor(() =>
      expect(getActivityFeed).toHaveBeenLastCalledWith(
        expect.objectContaining({ actor: 'u-kiran', page: 1 }),
      ),
    );
  });

  it('asks for a custom range with both dates', async () => {
    getActivityScorecards.mockResolvedValue(cards);
    getActivityFeed.mockResolvedValue(feed([]));
    render(<ActivityReview />);
    await screen.findByText('Kiran Counsellor');
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }));
    await waitFor(() =>
      expect(getActivityScorecards).toHaveBeenLastCalledWith(
        expect.objectContaining({
          period: 'custom',
          since: expect.any(String),
          until: expect.any(String),
        }),
      ),
    );
    expect(await screen.findByText('Nothing recorded')).toBeInTheDocument();
  });
});
