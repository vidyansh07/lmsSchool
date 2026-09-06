import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BatchesHub } from '@/app/manage/batches/page';
import { ApiError } from '@/lib/api';
import type { ManageBatchRow } from '@/lib/manage';

const listManageBatches = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, listManageBatches };
});

vi.mock('@/components/manage/attention-strip', () => ({ ManagerAttentionStrip: () => null }));

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

function page(results: ManageBatchRow[]) {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function batchRow(overrides: Partial<ManageBatchRow> = {}): ManageBatchRow {
  return {
    id: 'batch-1',
    code: 'GRS-B-001',
    name: 'Morning Linux batch',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    trainer_name: 'Tina Trainer',
    start_date: '2026-04-01',
    end_date: '2026-06-01',
    capacity: 20,
    enrolled_count: 12,
    seats_available: 8,
    status: 'active',
    created_at: '2026-01-01',
    ...overrides,
  };
}

beforeEach(() => {
  listManageBatches.mockReset();
  push.mockReset();
});

describe('BatchesHub', () => {
  it('renders a batch row with its course and trainer', async () => {
    listManageBatches.mockResolvedValue(page([batchRow()]));
    render(<BatchesHub />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    expect(screen.getByText('Linux Essentials')).toBeInTheDocument();
    expect(screen.getByText('Tina Trainer')).toBeInTheDocument();
  });

  it('renders "Not assigned" for a batch with no trainer', async () => {
    listManageBatches.mockResolvedValue(page([batchRow({ trainer_name: '' })]));
    render(<BatchesHub />);
    await waitFor(() => expect(screen.getByText('Not assigned')).toBeInTheDocument());
  });

  it('renders "No data" for the dense columns the list endpoint does not carry yet', async () => {
    listManageBatches.mockResolvedValue(page([batchRow()]));
    render(<BatchesHub />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    // kind, attendance and DSR state are all absent on this row.
    expect(screen.getAllByText('No data').length).toBeGreaterThanOrEqual(2);
  });

  it('renders real attendance and plan-variance figures once the row carries them', async () => {
    listManageBatches.mockResolvedValue(
      page([batchRow({ attendance_percent: 76, timeline_status: 'behind', dsr_state: 'overdue' })]),
    );
    render(<BatchesHub />);
    await waitFor(() => expect(screen.getByText('76%')).toBeInTheDocument());
    expect(screen.getByText('Behind plan')).toBeInTheDocument();
  });

  it('marks a full batch', async () => {
    listManageBatches.mockResolvedValue(page([batchRow({ seats_available: 0 })]));
    render(<BatchesHub />);
    await waitFor(() => expect(screen.getByText('Full')).toBeInTheDocument());
  });

  it('shows an empty state when no batches match', async () => {
    listManageBatches.mockResolvedValue(page([]));
    render(<BatchesHub />);
    await waitFor(() => expect(screen.getByText('No batches match these filters')).toBeInTheDocument());
  });

  it('shows an error with retry on failure', async () => {
    listManageBatches.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load batches.', 'req-1'));
    render(<BatchesHub />);
    await waitFor(() => expect(screen.getByText('Could not load batches.')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('sends a search to the server rather than filtering in the browser', async () => {
    listManageBatches.mockResolvedValue(page([batchRow()]));
    render(<BatchesHub />);
    await waitFor(() => expect(listManageBatches).toHaveBeenCalledTimes(1));
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Search'), 'linux');
    await waitFor(() =>
      expect(listManageBatches).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'linux' })),
    );
  });

  it('sends a status filter to the server', async () => {
    listManageBatches.mockResolvedValue(page([batchRow()]));
    render(<BatchesHub />);
    await waitFor(() => expect(listManageBatches).toHaveBeenCalledTimes(1));
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText('Status'), 'active');
    await waitFor(() =>
      expect(listManageBatches).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'active' })),
    );
  });

  it('navigates to the batch on row activation', async () => {
    listManageBatches.mockResolvedValue(page([batchRow()]));
    render(<BatchesHub />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByText('Morning Linux batch'));
    expect(push).toHaveBeenCalledWith('/manage/batches/batch-1');
  });
});
