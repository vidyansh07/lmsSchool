/**
 * `/admin/batches` — the admin/trainer batch list, migrated onto `DataTable`
 * (Phase R6). Covers what the migration must not have changed: every column
 * still renders real data, sort/pagination still call `listBatches` with the
 * same query shape, and the density toggle persists.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminBatchesPage from '@/app/admin/batches/page';
import { ApiError } from '@/lib/api';
import type { BatchListRow } from '@/types/api';

const listBatches = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, listBatches };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

vi.mock('@/components/export-menu', () => ({ ExportMenu: () => null }));
vi.mock('@/app/admin/batches/create-batch-dialog', () => ({ CreateBatchDialog: () => null }));

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

function page(results: BatchListRow[]) {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function batchRow(overrides: Partial<BatchListRow> = {}): BatchListRow {
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
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    can: () => true,
    user: { role: 'admin', capabilities: ['batch.view_any', 'batch.create'] },
  });
});

describe('AdminBatchesPage', () => {
  it('renders every column with real data', async () => {
    listBatches.mockResolvedValue(page([batchRow()]));
    render(<AdminBatchesPage />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    expect(screen.getByText('GRS-B-001')).toBeInTheDocument();
    expect(screen.getByText('Linux Essentials')).toBeInTheDocument();
    expect(screen.getByText('Tina Trainer')).toBeInTheDocument();
    expect(screen.getByText('12 / 20')).toBeInTheDocument();
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0);
  });

  it('marks a full batch', async () => {
    listBatches.mockResolvedValue(page([batchRow({ seats_available: 0 })]));
    render(<AdminBatchesPage />);
    await waitFor(() => expect(screen.getByText('Full')).toBeInTheDocument());
  });

  it('sends a search to the server rather than filtering in the browser', async () => {
    listBatches.mockResolvedValue(page([batchRow()]));
    render(<AdminBatchesPage />);
    await waitFor(() => expect(listBatches).toHaveBeenCalledTimes(1));
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Search'), 'linux');
    await waitFor(() =>
      expect(listBatches).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'linux', page: 1 }),
        expect.anything(),
      ),
    );
  });

  it('sends the same sort field toggleSort always has, on the same server request', async () => {
    listBatches.mockResolvedValue(page([batchRow()]));
    render(<AdminBatchesPage />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /runs/i }));
    await waitFor(() =>
      expect(listBatches).toHaveBeenLastCalledWith(
        expect.objectContaining({ ordering: 'start_date' }),
        expect.anything(),
      ),
    );
  });

  it('requests the next page through the same query shape', async () => {
    listBatches.mockResolvedValue({
      count: 40,
      page: 1,
      page_size: 20,
      total_pages: 2,
      next: 'x',
      previous: null,
      results: [batchRow()],
    });
    render(<AdminBatchesPage />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() =>
      expect(listBatches).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }), expect.anything()),
    );
  });

  it('navigates to the batch on row activation', async () => {
    listBatches.mockResolvedValue(page([batchRow()]));
    render(<AdminBatchesPage />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByText('Morning Linux batch'));
    expect(push).toHaveBeenCalledWith('/admin/batches/batch-1');
  });

  it('shows an error with retry on failure', async () => {
    listBatches.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load.', 'req-1'));
    render(<AdminBatchesPage />);
    await waitFor(() => expect(screen.getByText('Could not load batches')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('persists the density toggle across a re-render', async () => {
    listBatches.mockResolvedValue(page([batchRow()]));
    const { unmount } = render(<AdminBatchesPage />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /compact view/i }));
    expect(window.localStorage.getItem('grras.admin-batches-density')).toBe('compact');
    unmount();

    render(<AdminBatchesPage />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /comfortable view/i })).toBeInTheDocument();
  });
});
