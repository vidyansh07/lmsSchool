import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DsrReviewQueue } from '@/components/manage/dsr-review-queue';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import type { ManageDsrRow } from '@/lib/manage';

const listBatchDsr = vi.hoisted(() => vi.fn());
const reviewDsr = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, listBatchDsr, reviewDsr };
});

const mockAuth = vi.hoisted(() => ({ value: { can: () => true } as { can: (capability: string) => boolean } }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => mockAuth.value }));

function page(results: ManageDsrRow[]) {
  return { count: results.length, page: 1, page_size: 10, total_pages: 1, next: null, previous: null, results };
}

function dsrRow(overrides: Partial<ManageDsrRow> = {}): ManageDsrRow {
  return {
    id: 'dsr-1',
    batch_code: 'GRS-B-001',
    trainer_name: 'Tina Trainer',
    trainer_code: 'GRS-T-001',
    report_date: '2026-09-01',
    actual_topic: 'Linux permissions',
    status: 'submitted',
    submitted_at: '2026-09-01T18:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  listBatchDsr.mockReset();
  reviewDsr.mockReset();
  mockAuth.value = { can: () => true };
});

describe('DsrReviewQueue', () => {
  it('shows a loading state before the queue arrives', () => {
    listBatchDsr.mockReturnValue(new Promise(() => {}));
    render(<DsrReviewQueue batchId="batch-1" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error with retry when the queue fails to load', async () => {
    listBatchDsr.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load.', 'req-1'));
    render(<DsrReviewQueue batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Could not load.')).toBeInTheDocument());
  });

  it('says plainly that nothing is awaiting review', async () => {
    listBatchDsr.mockResolvedValue(page([]));
    render(<DsrReviewQueue batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Nothing awaiting review')).toBeInTheDocument());
  });

  it('renders each report awaiting review with its trainer and topic', async () => {
    listBatchDsr.mockResolvedValue(page([dsrRow()]));
    render(<DsrReviewQueue batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());
    expect(screen.getByText('Linux permissions')).toBeInTheDocument();
  });

  it('hides the approve control from someone without review authority', async () => {
    mockAuth.value = { can: () => false };
    listBatchDsr.mockResolvedValue(page([dsrRow()]));
    render(<DsrReviewQueue batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
  });

  it('approves inline: calls the review endpoint, removes the row and notifies the parent', async () => {
    const onReviewed = vi.fn();
    listBatchDsr.mockResolvedValue(page([dsrRow()]));
    reviewDsr.mockResolvedValue(dsrRow({ status: 'approved' }));
    const user = userEvent.setup();
    render(<DsrReviewQueue batchId="batch-1" onReviewed={onReviewed} />);
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /approve/i }));

    expect(reviewDsr).toHaveBeenCalledWith('dsr-1', 'approved');
    await waitFor(() => expect(screen.getByText('Nothing awaiting review')).toBeInTheDocument());
    expect(onReviewed).toHaveBeenCalledOnce();
  });

  it('rolls back visibly when the approval fails, and does not notify the parent', async () => {
    const onReviewed = vi.fn();
    listBatchDsr.mockResolvedValue(page([dsrRow()]));
    reviewDsr.mockRejectedValue(new ApiError(409, 'conflict', 'This report was already reviewed.', 'req-2'));
    const user = userEvent.setup();
    render(<DsrReviewQueue batchId="batch-1" onReviewed={onReviewed} />);
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /approve/i }));

    // The row reappears with the failure reason next to it, rather than being
    // left removed while the report is still sitting there unreviewed.
    await waitFor(() => expect(screen.getByText('This report was already reviewed.')).toBeInTheDocument());
    expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument();
    expect(onReviewed).not.toHaveBeenCalled();
  });
});

// The capability used to gate the approve control — asserted once so a rename
// of `Capability.dsrReview` upstream is caught here rather than by a
// silently-vanished button in production.
describe('DsrReviewQueue capability', () => {
  it('gates on dsr.review', () => {
    expect(Capability.dsrReview).toBe('dsr.review');
  });
});
